"""MemoryKernel — evidence-gated claims system (DEPRECATED).

This module is part of the deprecated ``memoryx.core`` namespace.
All new code should use ``MemoryRepository`` from ``memoryx.storage``
for memory operations.

For backward compatibility, MemoryKernel accepts either a database path
string (legacy — opens its own sync sqlite3 connection) or a MemoryRepository
instance (preferred — shares the async connection).

Migration path:
  Old: kernel = MemoryKernel("path/to/db")
  New: repo = MemoryRepository(Path("path/to/db"))
       kernel = MemoryKernel(repository=repo)
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
import warnings
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from memoryx.cognitive.conflict import new_conflict_group_id
from .schema import apply_schema

if TYPE_CHECKING:
    from memoryx.storage.repository import MemoryRepository

logger = logging.getLogger(__name__)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class MemoryKernel:
    """Evidence-gated claims kernel (legacy, deprecated).

    Accepts either a database path (sync mode) or a MemoryRepository
    (async-safe mode via shared connection).
    """

    def __init__(
        self,
        db: str | None = None,
        *,
        repository: MemoryRepository | None = None,
    ):
        if repository is not None:
            # Preferred: use MemoryRepository for connection management
            self._repo = repository
            self._conn = None
            self.db = str(repository.db.db_path) if repository.db else ":memory:"
            self._init_via_repo()
        elif db is not None:
            # Legacy: direct sync sqlite3 connection
            warnings.warn(
                "MemoryKernel(db_path) is deprecated. "
                "Use MemoryKernel(repository=repo) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self._repo = None
            self._conn = sqlite3.connect(db)
            self._conn.row_factory = sqlite3.Row
            self.db = db
            apply_schema(self._conn)
        else:
            raise ValueError("Either db (path) or repository must be provided")

    def _init_via_repo(self) -> None:
        """Initialize schema via the repository's connection."""
        if self._repo is None:
            return
        try:
            # Use the repository's async connection directly for schema setup
            conn = self._repo.db._require_conn()
            apply_schema(conn)
        except Exception:
            logger.warning("Failed to apply kernel schema via repository", exc_info=True)

    @property
    def conn(self) -> sqlite3.Connection:
        """Get the underlying SQLite connection.

        When using a repository, returns the repository's sync connection.
        """
        if self._repo is not None:
            return self._repo.db._require_conn()
        if self._conn is None:
            raise RuntimeError("MemoryKernel connection is closed")
        return self._conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        # Repository-managed connections are not closed here

    def create_evidence(
        self,
        source_type: str,
        content: str,
        session_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        evidence_id = str(uuid.uuid4())
        conn = self.conn
        conn.execute(
            "INSERT INTO evidence_events(evidence_id, source_type, session_id, agent_id, user_id, content, content_hash, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (evidence_id, source_type, session_id, agent_id, user_id, content, content_hash(content), json.dumps(metadata or {}, ensure_ascii=False)),
        )
        conn.commit()
        return evidence_id

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM evidence_events WHERE evidence_id = ?", (evidence_id,)).fetchone()
        return dict(row) if row else None

    def create_claim(
        self,
        claim_type: str,
        content: str,
        evidence_ids: list[str],
        confidence: float = 0.5,
        importance: float = 0.5,
    ) -> str:
        claim_id = str(uuid.uuid4())
        now = utc_iso()
        eids_str = ",".join(evidence_ids)
        conn = self.conn
        conn.execute(
            "INSERT INTO claims(claim_id, claim_type, content, status, confidence, importance, created_at, updated_at, source_evidence_ids) VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)",
            (claim_id, claim_type, content, confidence, importance, now, now, eids_str),
        )
        conn.execute("INSERT INTO fts_memories(claim_id, content) VALUES (?, ?)", (claim_id, content))
        self._write_version(claim_id, evidence_ids, "create", None, self.get_claim(claim_id), "create")
        conn.commit()
        return claim_id

    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        return dict(row) if row else None

    def list_claims(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute("SELECT * FROM claims WHERE status = ? ORDER BY created_at ASC", (status,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM claims ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]

    def update_claim(
        self,
        claim_id: str,
        content: str | None = None,
        confidence: float | None = None,
        importance: float | None = None,
        evidence_ids: list[str] | None = None,
        reason: str = "update",
    ) -> None:
        before = self.get_claim(claim_id)
        if not before:
            raise ValueError(f"claim not found: {claim_id}")
        next_c = content if content is not None else before["content"]
        next_conf = confidence if confidence is not None else before["confidence"]
        next_imp = importance if importance is not None else before["importance"]
        conn = self.conn
        conn.execute(
            "UPDATE claims SET content = ?, confidence = ?, importance = ?, updated_at = ? WHERE claim_id = ?",
            (next_c, next_conf, next_imp, utc_iso(), claim_id),
        )
        if content is not None and content != before["content"]:
            conn.execute("DELETE FROM fts_memories WHERE claim_id = ?", (claim_id,))
            conn.execute("INSERT INTO fts_memories(claim_id, content) VALUES (?, ?)", (claim_id, content))
        self._write_version(claim_id, evidence_ids or [], "update", before, self.get_claim(claim_id), reason)
        conn.commit()

    def revoke_claim(self, claim_id: str, reason: str = "revoke") -> None:
        before = self.get_claim(claim_id)
        if not before:
            raise ValueError(f"claim not found: {claim_id}")
        conn = self.conn
        conn.execute("UPDATE claims SET status = 'revoked', updated_at = ? WHERE claim_id = ?", (utc_iso(), claim_id))
        self._write_version(claim_id, [], "revoke", before, self.get_claim(claim_id), reason)
        conn.commit()

    def supersede_claim(
        self,
        old_claim_id: str,
        new_claim_type: str,
        new_content: str,
        evidence_ids: list[str],
        reason: str = "supersede",
        confidence: float = 0.7,
        importance: float = 0.5,
    ) -> str:
        before = self.get_claim(old_claim_id)
        if not before:
            raise ValueError(f"claim not found: {old_claim_id}")
        new_id = self.create_claim(
            claim_type=new_claim_type,
            content=new_content,
            evidence_ids=evidence_ids,
            confidence=confidence,
            importance=importance,
        )
        conn = self.conn
        conn.execute(
            "UPDATE claims SET status = 'superseded', superseded_by = ?, updated_at = ? WHERE claim_id = ?",
            (new_id, utc_iso(), old_claim_id),
        )
        self.add_claim_edge(new_id, old_claim_id, "supersedes", reason=reason)
        self._write_version(old_claim_id, evidence_ids, "supersede", before, self.get_claim(old_claim_id), reason)
        conn.commit()
        return new_id

    def reinforce_claim(
        self,
        claim_id: str,
        evidence_ids: list[str] | None = None,
        reason: str = "reinforce",
        confidence_delta: float = 0.03,
        importance_delta: float = 0.01,
    ) -> None:
        before = self.get_claim(claim_id)
        if not before:
            raise ValueError(f"claim not found: {claim_id}")
        conn = self.conn
        conn.execute(
            "UPDATE claims SET confidence = MIN(1.0, confidence + ?), importance = MIN(1.0, importance + ?), updated_at = ? WHERE claim_id = ?",
            (confidence_delta, importance_delta, utc_iso(), claim_id),
        )
        self._write_version(claim_id, evidence_ids or [], "reinforce", before, self.get_claim(claim_id), reason)
        conn.commit()

    def mark_conflict(self, claim_a_id: str, claim_b_id: str, reason: str = "conflict") -> str:
        group_id = new_conflict_group_id()
        ba = self.get_claim(claim_a_id)
        bb = self.get_claim(claim_b_id)
        if not ba or not bb:
            raise ValueError("both claims must exist")
        conn = self.conn
        for cid in (claim_a_id, claim_b_id):
            conn.execute(
                "UPDATE claims SET status = 'conflicted', contradiction_group_id = ?, updated_at = ? WHERE claim_id = ?",
                (group_id, utc_iso(), cid),
            )
        self.add_claim_edge(claim_a_id, claim_b_id, "conflicts_with", reason=reason)
        self._write_version(claim_a_id, [], "conflict", ba, self.get_claim(claim_a_id), reason)
        self._write_version(claim_b_id, [], "conflict", bb, self.get_claim(claim_b_id), reason)
        conn.commit()
        return group_id

    def resolve_conflict(self, conflict_group_id: str, winning_claim_id: str, reason: str = "resolve_conflict") -> None:
        rows = self.conn.execute(
            "SELECT claim_id FROM claims WHERE contradiction_group_id = ?", (conflict_group_id,)
        ).fetchall()
        if not rows:
            raise ValueError(f"conflict group not found: {conflict_group_id}")
        conn = self.conn
        for row in rows:
            cid = row["claim_id"]
            before = self.get_claim(cid)
            new_status = "active" if cid == winning_claim_id else "superseded"
            conn.execute("UPDATE claims SET status = ?, updated_at = ? WHERE claim_id = ?", (new_status, utc_iso(), cid))
            self._write_version(cid, [], "resolve_conflict", before, self.get_claim(cid), reason)
        conn.commit()

    def add_claim_edge(self, from_claim_id: str, to_claim_id: str, edge_type: str, reason: str | None = None) -> str:
        edge_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO claim_edges(edge_id, from_claim_id, to_claim_id, edge_type, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (edge_id, from_claim_id, to_claim_id, edge_type, reason, utc_iso()),
        )
        return edge_id

    def get_claim_versions(self, claim_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM claim_versions WHERE claim_id = ? ORDER BY created_at ASC", (claim_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def _write_version(
        self,
        claim_id: str,
        evidence_ids: list[str],
        operation: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        reason: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO claim_versions(version_id, claim_id, evidence_ids, operation, before_json, after_json, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), claim_id, ",".join(evidence_ids), operation, json.dumps(before or {}, ensure_ascii=False), json.dumps(after or {}, ensure_ascii=False), reason),
        )