"""MemoryKernel — write / version / state management for claims + evidence."""

import json
import sqlite3
import uuid
from typing import Any

from .schema import apply_schema


class MemoryKernel:
    """Core memory kernel — evidence ingestion, claim creation, version history."""

    def __init__(self, db: str) -> None:
        self.db = db
        self.conn = sqlite3.connect(db)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        apply_schema(self.conn)

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def create_evidence(
        self,
        source_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """Append an evidence event. Returns the generated evidence_id."""
        ev_id = str(uuid.uuid4())
        content_hash = str(uuid.uuid5(uuid.NAMESPACE_DNS, content))
        self.conn.execute(
            """INSERT INTO evidence_events
               (evidence_id, source_type, session_id, agent_id, user_id,
                content, content_hash, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ev_id, source_type, session_id, agent_id, user_id,
             content, content_hash, json.dumps(metadata or {})),
        )
        self.conn.commit()
        return ev_id

    # ------------------------------------------------------------------
    # Claims
    # ------------------------------------------------------------------

    def create_claim(
        self,
        claim_type: str,
        content: str,
        evidence_ids: list[str] | None = None,
        confidence: float = 0.5,
        importance: float = 0.5,
    ) -> str:
        """Create a new active claim and its FTS entry. Returns claim_id."""
        claim_id = str(uuid.uuid4())
        now = self._now()

        self.conn.execute(
            """INSERT INTO claims
               (claim_id, claim_type, content, status,
                confidence, importance,
                created_at, updated_at)
               VALUES (?, ?, ?, 'active', ?, ?, ?, ?)""",
            (claim_id, claim_type, content,
             confidence, importance,
             now, now),
        )

        self.conn.execute(
            "INSERT INTO fts_memories (claim_id, content) VALUES (?, ?)",
            (claim_id, content),
        )

        self._write_version(claim_id, evidence_ids or [], "create", None, {
            "claim_type": claim_type,
            "content": content,
            "confidence": confidence,
            "importance": importance,
        })

        self.conn.commit()
        return claim_id

    def revoke_claim(self, claim_id: str, reason: str = "") -> None:
        """Revoke an active claim (status → revoked)."""
        row = self.conn.execute(
            "SELECT content, claim_type FROM claims WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Claim {claim_id} not found")
        before = {"content": row[0], "claim_type": row[1]}

        self.conn.execute(
            "UPDATE claims SET status = 'revoked', updated_at = ? WHERE claim_id = ?",
            (self._now(), claim_id),
        )
        self._write_version(claim_id, [], "revoke", before, {
            "status": "revoked",
            "reason": reason,
        }, reason=reason)
        self.conn.commit()

    def supersede_claim(
        self,
        old_claim_id: str,
        new_claim_id: str,
        reason: str = "",
    ) -> None:
        """Mark old_claim_id as superseded in favour of new_claim_id."""
        row = self.conn.execute(
            "SELECT content FROM claims WHERE claim_id = ?",
            (old_claim_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Claim {old_claim_id} not found")

        self.conn.execute(
            "UPDATE claims SET status = 'superseded', updated_at = ? WHERE claim_id = ?",
            (self._now(), old_claim_id),
        )
        self._write_version(old_claim_id, [], "supersede",
                           {"content": row[0]},
                           {"superseded_by": new_claim_id, "reason": reason})
        self.conn.commit()

    def get_claim(self, claim_id: str) -> dict | None:
        """Fetch a claim by ID. Returns None if not found."""
        row = self.conn.execute(
            """SELECT claim_id, claim_type, content, status,
                      confidence, importance,
                      valid_from, valid_to, created_at, updated_at
               FROM claims WHERE claim_id = ?""",
            (claim_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "claim_id": row[0],
            "claim_type": row[1],
            "content": row[2],
            "status": row[3],
            "confidence": row[4],
            "importance": row[5],
            "valid_from": row[6],
            "valid_to": row[7],
            "created_at": row[8],
            "updated_at": row[9],
        }

    def list_versions(self, claim_id: str) -> list[dict]:
        """Return the version history for a given claim."""
        rows = self.conn.execute(
            """SELECT version_id, claim_id, evidence_ids, operation,
                      before_json, after_json, reason, created_at
               FROM claim_versions
               WHERE claim_id = ?
               ORDER BY created_at ASC""",
            (claim_id,),
        ).fetchall()
        return [
            {
                "version_id": r[0],
                "claim_id": r[1],
                "evidence_ids": r[2].split(",") if r[2] else [],
                "operation": r[3],
                "before": json.loads(r[4]) if r[4] else None,
                "after": json.loads(r[5]) if r[5] else None,
                "reason": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_version(
        self,
        claim_id: str,
        evidence_ids: list[str],
        operation: str,
        before: Any,
        after: Any,
        reason: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO claim_versions
               (version_id, claim_id, evidence_ids, operation, before_json, after_json, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), claim_id,
             ",".join(evidence_ids),
             operation,
             json.dumps(before) if before else None,
             json.dumps(after) if after else None,
             reason),
        )

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
