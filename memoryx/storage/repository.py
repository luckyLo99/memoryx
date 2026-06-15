from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .migrations import MigrationManager
from .sqlite_async import AsyncSQLite
from .record import MemoryRecord
from .fts_utils import tokenize_query_terms, build_fts_query, expand_with_aliases

import logging
logger = logging.getLogger(__name__)


MEMORY_TYPES = {
    "FACT", "EXPERIENCE", "OBSERVATION", "OPINION", "PREFERENCE",
    "PROJECT", "TASK", "RELATION", "EPISODIC", "ENT_RELATION", "PERSONA",
    "OPINION_SHIFT", "LESSON",
}

# === 24.6-B: chunking helper for batch IN queries =============================
_BATCH_HYDRATION_CHUNK_SIZE = 500


def _chunked(items: list[str], size: int) -> list[list[str]]:
    """Yield items in chunks of `size`."""
    return [items[i:i + size] for i in range(0, len(items), size)]


# Re-export for backward compatibility
_MemoryRecord = MemoryRecord


class MemoryRepository:
    def __init__(self, db_path: Path, time_provider=None) -> None:
        self.db = AsyncSQLite(db_path)
        self.migrations = MigrationManager(db=self.db)
        if time_provider is None:
            from memoryx.temporal.time_provider import get_time_provider
            time_provider = get_time_provider()
        self._time_provider = time_provider

    async def open(self) -> None:
        await self.db.open()
        await self.migrations.ensure_schema()

    async def close(self) -> None:
        await self.db.close()

    @staticmethod
    def checksum(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _now_iso(self) -> str:
        return self._time_provider.now().isoformat()

    def _normalize_record(self, record: MemoryRecord) -> MemoryRecord:
        if record.memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unsupported memory_type: {record.memory_type}")
        if not record.id:
            record.id = uuid4().hex
        if not record.content_hash:
            record.content_hash = self.checksum(record.content)
        if not record.checksum:
            record.checksum = self.checksum(record.content)
        if not record.valid_from:
            record.valid_from = self._now_iso()
        if record.active_state not in ("active", "archived", "superseded", "quarantined"):
            record.active_state = "active"
        return record

    @staticmethod
    def _normalize_search_query(query: str) -> str:
        tokens = [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in query).split() if t]
        return " OR ".join(tokens) if tokens else ""

    async def count_memories(self) -> int:
        """Return the total number of active (non-archived) memories."""
        async with self.db.acquire() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM memories WHERE active_state != 'archived';")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    async def archive_oldest_memories(self, limit: int = 100) -> int:
        """Archive the oldest, least-important memories to control storage growth.

        Returns the number of memories archived.
        """
        archived = 0
        now = self._now_iso()
        async with self.db.transaction(mode="IMMEDIATE") as conn:
            # Select candidates: low importance, low access, oldest updated
            cur = conn.execute(
                """SELECT id, content, content_hash FROM memories
                   WHERE active_state = 'active'
                   ORDER BY importance_score ASC, access_count ASC, updated_at ASC
                   LIMIT ?;""",
                (limit,),
            )
            rows = cur.fetchall()
            for row in rows:
                mem_id, content, content_hash = row
                conn.execute(
                    """INSERT INTO archived_memories
                       (id, memory_id, content, archived_reason, archived_at, checksum, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                       content=excluded.content, archived_at=excluded.archived_at;""",
                    (uuid4().hex, mem_id, content or "",
                     "auto_archive: storage limit", now,
                     content_hash or self.checksum(content or ""), "{}"),
                )
                conn.execute(
                    "UPDATE memories SET active_state = 'archived', archived_at = ? WHERE id = ?;",
                    (now, mem_id),
                )
                archived += 1
        return archived

    async def _maybe_auto_archive(self, max_memories: int | None = None,
                                   threshold_pct: float | None = None) -> int:
        """Check if memory count exceeds threshold and auto-archive if needed."""
        if max_memories is None or threshold_pct is None:
            try:
                from memoryx.config import get_settings
                settings = get_settings()
                max_memories = max_memories if max_memories is not None else settings.max_memories
                threshold_pct = threshold_pct if threshold_pct is not None else settings.auto_archive_threshold_pct
            except Exception:
                max_memories = max_memories if max_memories is not None else 100_000
                threshold_pct = threshold_pct if threshold_pct is not None else 0.9
        threshold = int(max_memories * threshold_pct)
        count = await self.count_memories()
        if count > threshold:
            overage = count - threshold + 1000  # archive 1k extra for headroom
            return await self.archive_oldest_memories(limit=min(overage, 5000))
        return 0

    async def store_memory(self, record: MemoryRecord) -> str:
        """Store one memory atomically using BEGIN IMMEDIATE via self.db.transaction(mode='IMMEDIATE').

        Atomic write set: memories + memory_versions + audit_logs.
        """
        n = self._normalize_record(record)
        now = self._now_iso()

        async with self.db.transaction(mode="IMMEDIATE") as conn:
            conn.execute(
                """INSERT INTO memories (id,session_id,memory_type,content,content_summary,content_hash,checksum,
                importance_score,confidence_score,decay_score,recency_score,access_count,reinforcement_score,safety_score,
                active_state,superseded_by,contradiction_group_id,valid_from,valid_to,archived_at,scope,tags_json,entities_json,created_at,updated_at,metadata_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET content=excluded.content,content_hash=excluded.content_hash,
                checksum=excluded.checksum,importance_score=excluded.importance_score,confidence_score=excluded.confidence_score,
                decay_score=excluded.decay_score,recency_score=excluded.recency_score,access_count=excluded.access_count,
                reinforcement_score=excluded.reinforcement_score,safety_score=excluded.safety_score,
                active_state=excluded.active_state,superseded_by=excluded.superseded_by,
                contradiction_group_id=excluded.contradiction_group_id,valid_from=excluded.valid_from,
                valid_to=excluded.valid_to,archived_at=excluded.archived_at,updated_at=datetime('now'),
                metadata_json=excluded.metadata_json,content_summary=excluded.content_summary,
                session_id=excluded.session_id,memory_type=excluded.memory_type,
                scope=excluded.scope,tags_json=excluded.tags_json,entities_json=excluded.entities_json;""",
                (n.id,n.session_id,n.memory_type,n.content,n.content_summary,n.content_hash,n.checksum,
                 n.importance_score,n.confidence_score,n.decay_score,n.recency_score,n.access_count,
                 n.reinforcement_score,n.safety_score,n.active_state,n.superseded_by,n.contradiction_group_id,
                 n.valid_from,n.valid_to,n.archived_at,n.scope,n.tags_json,n.entities_json,now,now,n.metadata_json))

            # Write memory_version
            cur = conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM memory_versions WHERE memory_id=?;",(n.id,))
            next_ver = int(cur.fetchone()[0])
            now = self._now_iso()
            conn.execute(
                "INSERT INTO memory_versions(id,memory_id,version,content,content_hash,checksum,valid_from,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?);",
                (uuid4().hex,n.id,next_ver,n.content,n.content_hash,n.checksum,n.valid_from or now,now,"{}"))

            # Write audit_log
            conn.execute(
                "INSERT INTO audit_logs(id,entity_type,entity_id,action,after_json,checksum,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?);",
                (uuid4().hex,"memories",n.id,"store_memory",
                 json.dumps({"memory_type":n.memory_type,"checksum":n.checksum}),
                 self.checksum(f"{n.id}:store_memory:{now}"),now,"{}"))

        # Auto-archive check (non-blocking, runs outside the write tx)
        try:
            await self._maybe_auto_archive()
        except Exception:
            logger.warning("Auto-archive check failed", exc_info=True)

        return n.id

    async def store_memories(self, records: list[MemoryRecord]) -> int:
        if not records:
            return 0
        async with self.db.transaction():
            conn = self.db._require_conn()
            now = self._now_iso()
            for r in records:
                n = self._normalize_record(r)
                conn.execute("""INSERT INTO memories (id,session_id,memory_type,content,content_summary,content_hash,checksum,
                importance_score,confidence_score,decay_score,recency_score,access_count,reinforcement_score,safety_score,
                active_state,superseded_by,contradiction_group_id,valid_from,valid_to,archived_at,scope,tags_json,entities_json,created_at,updated_at,metadata_json)
                VALUES (:id,:sid,:mt,:c,:cs,:ch,:ck,:is,:cf,:ds,:rs,:ac,:rf,:sf,:as,:sb,:cg,:vf,:vt,:aa,:sc,:tj,:ej,:now,:now,:mj)
                ON CONFLICT(id) DO UPDATE SET content=excluded.content,content_hash=excluded.content_hash,
                checksum=excluded.checksum,importance_score=excluded.importance_score,confidence_score=excluded.confidence_score,
                decay_score=excluded.decay_score,recency_score=excluded.recency_score,access_count=excluded.access_count,
                reinforcement_score=excluded.reinforcement_score,safety_score=excluded.safety_score,
                active_state=excluded.active_state,superseded_by=excluded.superseded_by,
                contradiction_group_id=excluded.contradiction_group_id,valid_from=excluded.valid_from,
                valid_to=excluded.valid_to,archived_at=excluded.archived_at,updated_at=:now,
                metadata_json=excluded.metadata_json,content_summary=excluded.content_summary,
                session_id=excluded.session_id,memory_type=excluded.memory_type,
                scope=excluded.scope,tags_json=excluded.tags_json,entities_json=excluded.entities_json;""",
                {"id":n.id,"sid":n.session_id,"mt":n.memory_type,"c":n.content,"cs":n.content_summary,
                 "ch":n.content_hash,"ck":n.checksum,"is":n.importance_score,"cf":n.confidence_score,
                 "ds":n.decay_score,"rs":n.recency_score,"ac":n.access_count,"rf":n.reinforcement_score,
                 "sf":n.safety_score,"as":n.active_state,"sb":n.superseded_by,"cg":n.contradiction_group_id,
                 "vf":n.valid_from,"vt":n.valid_to,"aa":n.archived_at,"sc":n.scope,"tj":n.tags_json,"ej":n.entities_json,"mj":n.metadata_json,"now":now})
                ver = int(conn.execute("SELECT COALESCE(MAX(version),0) FROM memory_versions WHERE memory_id=?;",(n.id,)).fetchone()[0])+1
                conn.execute("INSERT INTO memory_versions(id,memory_id,version,content,content_hash,checksum,valid_from,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?);",
                    (uuid4().hex,n.id,ver,n.content,n.content_hash,n.checksum,now,now,"{}"))
                conn.execute("INSERT INTO audit_logs(id,entity_type,entity_id,action,after_json,checksum,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?);",
                    (uuid4().hex,"memories",n.id,"store_memory",json.dumps({"memory_type":n.memory_type,"checksum":n.checksum}),n.checksum,now,"{}"))
        return len(records)

    async def write_version(self, memory_id: str, content: str, checksum_val: str) -> None:
        row = await self.db.fetchone("SELECT COALESCE(MAX(version),0) AS version FROM memory_versions WHERE memory_id=?;",(memory_id,))
        next_v = int(row["version"] if row else 0)+1
        now = self._now_iso()
        ch = self.checksum(content)
        await self.db.execute("INSERT INTO memory_versions(id,memory_id,version,content,content_hash,checksum,valid_from,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?);",
            (uuid4().hex,memory_id,next_v,content,ch,checksum_val or ch,now,now,"{}"))


    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        """Convert a DB row to dict, adding memory_id alias for id."""
        d = dict(row)
        if 'id' in d and 'memory_id' not in d:
            d['memory_id'] = d['id']
        return d

    async def get_memory(self, memory_id: str) -> dict[str,Any]|None:
        row = await self.db.fetchone("SELECT * FROM memories WHERE id=?;",(memory_id,))
        return self._row_to_dict(row) if row else None

    async def batch_get_memories(
        self,
        memory_ids: list[str],
        *,
        batch_size: int = _BATCH_HYDRATION_CHUNK_SIZE,
    ) -> dict[str, dict[str, Any]]:
        """Return dict[id, memory] for a batch of memory IDs (24.6-B).

        Uses parameterised IN queries with chunking to respect SQLite
        host parameter limits.  Empty / duplicate input are handled safely.
        """
        if not memory_ids:
            return {}
        # Deduplicate while preserving first-occurrence order
        seen: set[str] = set()
        ordered: list[str] = []
        for mid in memory_ids:
            if mid not in seen:
                seen.add(mid)
                ordered.append(mid)
        result: dict[str, dict[str, Any]] = {}
        for chunk in _chunked(ordered, batch_size):
            placeholders = ",".join(["?"] * len(chunk))
            sql = f"SELECT * FROM memories WHERE id IN ({placeholders})"  # nosec B608
            rows = await self.db.fetchall(sql, tuple(chunk))
            for row in rows:
                d = self._row_to_dict(row)
                result[d["memory_id"]] = d
        return result

    async def list_memories(self, limit: int=1000) -> list[dict[str,Any]]:
        rows = await self.db.fetchall("SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?;",(limit,))
        return [self._row_to_dict(r) for r in rows]

    async def list_active_memories(self, limit: int=100) -> list[dict[str,Any]]:
        rows = await self.db.fetchall("SELECT * FROM memories WHERE active_state='active' ORDER BY importance_score DESC, updated_at DESC LIMIT ?;",(limit,))
        return [self._row_to_dict(r) for r in rows]

    async def search_full_text(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Full-text search with fallback plan: phrase → AND → OR → alias OR → fuzzy.

        When FTS5 returns no matches, we expand the token list with
        synonyms/typo aliases and run a second pass.
        """
        tokens = tokenize_query_terms(query)
        if not tokens:
            return []

        plans: list[tuple[str, str]] = []
        phrase_q = build_fts_query(tokens, "PHRASE")
        if phrase_q:
            plans.append(("phrase", phrase_q))
        and_q = build_fts_query(tokens, "AND")
        if and_q and and_q != phrase_q:
            plans.append(("and", and_q))
        or_q = build_fts_query(tokens, "OR")
        if or_q and or_q not in (phrase_q, and_q):
            plans.append(("or", or_q))

        for _name, fts_q in plans:
            try:
                rows = await self.db.fetchall(
                    "SELECT m.* FROM memories m JOIN memories_fts f ON m.rowid=f.rowid "
                    "WHERE memories_fts MATCH ? ORDER BY bm25(memories_fts) LIMIT ?;",
                    (fts_q, limit),
                )
                if rows:
                    return [self._row_to_dict(r) for r in rows]
            except Exception:
                continue

        # --- P0-6: fuzzy / alias expansion when FTS5 returns zero ---
        try:
            from memoryx.retrieval.fuzzy_search import expand_query_with_fuzzy_aliases
        except Exception:
            expand_query_with_fuzzy_aliases = None  # type: ignore

        if expand_query_with_fuzzy_aliases is not None:
            expanded = expand_query_with_fuzzy_aliases(tokens)
            if expanded and set(expanded) != set(tokens):
                expanded_or = build_fts_query(expanded, "OR")
                try:
                    rows = await self.db.fetchall(
                        "SELECT m.* FROM memories m JOIN memories_fts f ON m.rowid=f.rowid "
                        "WHERE memories_fts MATCH ? ORDER BY bm25(memories_fts) LIMIT ?;",
                        (expanded_or, limit),
                    )
                    if rows:
                        return [self._row_to_dict(r) for r in rows]
                except Exception:
                    pass
        return []

    async def search_full_text_with_trace(
        self, query: str, limit: int = 20,
    ) -> tuple[list[dict[str, Any]], dict]:
        """Full-text search returning (results, trace).  Trace has:
        query_plan_used, fallback_steps, raw_hit_count.
        """
        tokens = tokenize_query_terms(query)
        if not tokens:
            return [], {"query_plan_used": None, "fallback_steps": [], "raw_hit_count": 0}

        plan_defs = [
            ("phrase", build_fts_query(tokens, "PHRASE")),
            ("and",    build_fts_query(tokens, "AND")),
            ("or",     build_fts_query(tokens, "OR")),
        ]
        expanded = expand_with_aliases(tokens)
        alias_q = build_fts_query(expanded, "OR")
        if alias_q and alias_q != plan_defs[-1][1]:
            plan_defs.append(("alias", alias_q))

        fallback_steps: list[str] = []
        for plan_name, fts_q in plan_defs:
            if not fts_q:
                continue
            try:
                rows = await self.db.fetchall(
                    "SELECT m.* FROM memories m JOIN memories_fts f ON m.rowid=f.rowid "
                    "WHERE memories_fts MATCH ? ORDER BY bm25(memories_fts) LIMIT ?;",
                    (fts_q, limit),
                )
                count = len(rows)
                if count > 0:
                    return [self._row_to_dict(r) for r in rows], {
                        "query_plan_used": plan_name,
                        "fallback_steps": fallback_steps,
                        "raw_hit_count": count,
                    }
                fallback_steps.append(f"{plan_name}:0")
            except Exception:
                fallback_steps.append(f"{plan_name}:error")
                continue

        # --- P0-6: fuzzy / alias expansion when FTS5 returns zero ---
        try:
            from memoryx.retrieval.fuzzy_search import expand_query_with_fuzzy_aliases
        except Exception:
            expand_query_with_fuzzy_aliases = None  # type: ignore

        if expand_query_with_fuzzy_aliases is not None:
            expanded = expand_query_with_fuzzy_aliases(tokens)
            if expanded and set(expanded) != set(tokens):
                fuzzy_q = build_fts_query(expanded, "OR")
                try:
                    rows = await self.db.fetchall(
                        "SELECT m.* FROM memories m JOIN memories_fts f ON m.rowid=f.rowid "
                        "WHERE memories_fts MATCH ? ORDER BY bm25(memories_fts) LIMIT ?;",
                        (fuzzy_q, limit),
                    )
                    count = len(rows)
                    if count > 0:
                        return [self._row_to_dict(r) for r in rows], {
                            "query_plan_used": "fuzzy",
                            "fallback_steps": fallback_steps,
                            "raw_hit_count": count,
                        }
                    fallback_steps.append("fuzzy:0")
                except Exception:
                    fallback_steps.append("fuzzy:error")

        return [], {
            "query_plan_used": None,
            "fallback_steps": fallback_steps,
            "raw_hit_count": 0,
        }

    async def search_memories_text(
        self, query: str, limit: int = 20,
        include_states: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search memories with optional active_state filter.

        include_states: if set, only return memories whose active_state is in this set.
        Default (None): only 'active' and 'archived' (excludes superseded/quarantined).
        """
        q = self._normalize_search_query(query)
        if not q:
            return []
        states = include_states if include_states is not None else {"active", "archived"}
        placeholders = ",".join("?" for _ in states)
        rows = await self.db.fetchall(
            f"SELECT m.* FROM memories m JOIN memories_fts f ON m.rowid=f.rowid "  # nosec B608
            f"WHERE memories_fts MATCH ? AND m.active_state IN ({placeholders}) "
            f"ORDER BY bm25(memories_fts) LIMIT ?;",
            (q, *states, limit),
        )
        return [self._row_to_dict(r) for r in rows]

    async def list_memories_filtered(
        self, limit: int = 20, memory_type: str | None = None,
        scope: str | None = None, include_states: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List memories with optional filtering.

        include_states: if set, only return memories whose active_state is in this set.
        Default (None): only 'active' and 'archived'.
        """
        conditions = []
        params: list[Any] = []
        states = include_states if include_states is not None else {"active", "archived"}
        state_placeholders = ",".join("?" for _ in states)
        conditions.append(f"active_state IN ({state_placeholders})")
        params.extend(states)
        if memory_type:
            conditions.append("memory_type=?")
            params.append(memory_type)
        if scope:
            conditions.append("scope=?")
            params.append(scope)
        where = " AND ".join(conditions)
        rows = await self.db.fetchall(
            f"SELECT * FROM memories WHERE {where} ORDER BY updated_at DESC LIMIT ?;",  # nosec B608
            (*params, limit),
        )
        return [self._row_to_dict(r) for r in rows]

    async def count_memories_by_state(self) -> dict[str, int]:
        """Return counts of memories grouped by active_state."""
        rows = await self.db.fetchall(
            "SELECT active_state, COUNT(*) AS cnt FROM memories GROUP BY active_state;"
        )
        return {r["active_state"]: r["cnt"] for r in rows}

    async def count_memories_by_type_scope(self) -> dict[str, dict[str, int]]:
        """Return counts grouped by memory_type -> scope."""
        rows = await self.db.fetchall(
            "SELECT memory_type, scope, COUNT(*) AS cnt FROM memories GROUP BY memory_type, scope ORDER BY memory_type;"
        )
        result: dict[str, dict[str, int]] = {}
        for r in rows:
            mt = r["memory_type"]
            sc = r["scope"]
            if mt not in result:
                result[mt] = {}
            result[mt][sc] = r["cnt"]
        return result

    async def count_memories_total(self) -> int:
        """Return total number of memories."""
        row = await self.db.fetchone("SELECT COUNT(*) AS cnt FROM memories;", ())
        return int(row["cnt"]) if row else 0

    async def count_memories_by_candidate_state(self) -> dict[str, int]:
        """Return counts grouped by candidate_state from metadata_json.

        Parses metadata_json for each memory.  Invalid/non-JSON metadata
        is counted under 'unknown'.  This is a read-only scan.
        """
        rows = await self.db.fetchall(
            "SELECT id, metadata_json FROM memories;", (),
        )
        counts: dict[str, int] = {}
        for r in rows:
            raw = r["metadata_json"]
            try:
                meta = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, ValueError):
                meta = {}
            cs = meta.get("candidate_state", "unknown")
            counts[cs] = counts.get(cs, 0) + 1
        return counts

    async def count_memories_by_evidence_level(self) -> dict[str, int]:
        """Return counts grouped by evidence_level from metadata_json.

        Read-only scan.  Invalid metadata -> 'unknown'.
        Missing evidence_level -> 'missing'.
        """
        rows = await self.db.fetchall(
            "SELECT id, metadata_json FROM memories;", (),
        )
        counts: dict[str, int] = {}
        for r in rows:
            raw = r["metadata_json"]
            try:
                meta = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, ValueError):
                counts["unknown"] = counts.get("unknown", 0) + 1
                continue
            el = meta.get("evidence_level", "missing")
            counts[el] = counts.get(el, 0) + 1
        return counts

    async def count_low_quality_candidates(self) -> dict[str, int]:
        """Return low-quality candidate statistics.

        Low quality = candidate_state=='candidate' AND
          evidence_level in {E0_MODEL_INFERENCE, missing, unknown}
          OR confidence < 0.3

        Returns dict with keys:
          low_quality_candidate_count, e0_candidate_count,
          missing_evidence_count, unknown_metadata_count
        """
        rows = await self.db.fetchall(
            "SELECT id, metadata_json, confidence_score FROM memories;", (),
        )
        low_quality = 0
        e0_candidate = 0
        missing_evidence = 0
        unknown_meta = 0

        for r in rows:
            raw = r["metadata_json"]
            try:
                meta = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, ValueError):
                unknown_meta += 1
                continue

            cs = meta.get("candidate_state", "")
            el = meta.get("evidence_level", "missing")
            conf = meta.get("confidence", r["confidence_score"] if "confidence_score" in r.keys() else 0.0)
            try:
                conf = float(conf)
            except (TypeError, ValueError):
                conf = 0.0

            if el == "missing":
                missing_evidence += 1
            if cs == "candidate" and el == "E0_MODEL_INFERENCE":
                e0_candidate += 1
            if cs == "candidate" and (
                el in ("E0_MODEL_INFERENCE", "missing", "unknown") or conf < 0.3
            ):
                low_quality += 1

        return {
            "low_quality_candidate_count": low_quality,
            "e0_candidate_count": e0_candidate,
            "missing_evidence_count": missing_evidence,
            "unknown_metadata_count": unknown_meta,
        }

    async def evidence_quality_summary(self) -> dict[str, Any]:
        """Return combined evidence quality summary.

        Combines evidence_level distribution, candidate_state distribution,
        and low-quality candidate counts into a single report.
        """
        by_el = await self.count_memories_by_evidence_level()
        by_cs = await self.count_memories_by_candidate_state()
        lq = await self.count_low_quality_candidates()
        return {
            "by_evidence_level": by_el,
            "by_candidate_state": by_cs,
            **lq,
        }

    async def count_memories_by_layer(self) -> dict[str, int]:
        """Return counts grouped by memory_layer from metadata_json.

        Read-only scan.  Invalid metadata -> 'unknown'.
        Missing memory_layer -> 'missing' (backward compat).
        """
        rows = await self.db.fetchall(
            "SELECT id, metadata_json FROM memories;", (),
        )
        counts: dict[str, int] = {}
        for r in rows:
            raw = r["metadata_json"]
            try:
                meta = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, ValueError):
                counts["unknown"] = counts.get("unknown", 0) + 1
                continue
            layer = meta.get("memory_layer", "missing")
            counts[layer] = counts.get(layer, 0) + 1
        return counts

    async def layer_quality_summary(self) -> dict[str, Any]:
        """Return combined layer quality summary.

        Includes by_memory_layer, missing_layer_count, unknown_layer_count.
        """
        by_layer = await self.count_memories_by_layer()
        missing = by_layer.pop("missing", 0)
        unknown = by_layer.pop("unknown", 0)
        return {
            "by_memory_layer": by_layer,
            "missing_layer_count": missing,
            "unknown_layer_count": unknown,
        }

    async def count_open_conflicts(self) -> int:
        """Return number of open (unresolved) conflicts."""
        rows = await self.db.fetchall(
            "SELECT COUNT(*) AS cnt FROM memory_conflicts WHERE resolved_state = 'open';", (),
        )
        return int(rows[0]["cnt"]) if rows else 0

    async def count_conflicts_by_state(self) -> dict[str, int]:
        """Return conflict counts grouped by resolved_state."""
        rows = await self.db.fetchall(
            "SELECT resolved_state, COUNT(*) AS cnt FROM memory_conflicts GROUP BY resolved_state;", (),
        )
        return {r["resolved_state"]: r["cnt"] for r in rows} if rows else {}

    async def record_access(self, memory_id: str) -> None:
        now = self._now_iso()
        await self.db.execute("UPDATE memories SET access_count=access_count+1, updated_at=? WHERE id=?;",(now,memory_id))
        await self.db.execute("INSERT INTO memory_access_logs(id,memory_id,access_type,checksum,created_at,metadata_json) VALUES (?,?,?,?,?,?);",
            (uuid4().hex,memory_id,"read",self.checksum(f"access:{memory_id}:{now}"),now,"{}"))

    async def supersede_memory(self, memory_id: str, superseded_by: str) -> None:
        now = self._now_iso()
        await self.db.execute("UPDATE memories SET active_state='superseded',superseded_by=?,valid_to=?,updated_at=? WHERE id=?;",(superseded_by,now,now,memory_id))
        await self.append_audit("memories",memory_id,"supersede_memory",after_json={"superseded_by":superseded_by})

    async def update_memory_metadata(self, memory_id: str, metadata_patch: dict) -> bool:
        """Update metadata_json by merging patch into existing metadata.

        Reads existing metadata_json, parses it, merges the patch dict on
        top (patch wins), and writes back.  Unknown fields in the existing
        metadata are preserved.  If metadata_json is empty or invalid JSON
        it is treated as {} with an internal repair warning.
        """
        row = await self.db.fetchone("SELECT metadata_json FROM memories WHERE id=?;", (memory_id,))
        if row is None:
            return False

        raw = row["metadata_json"]
        try:
            existing = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            existing = {"_metadata_repair_warning": "metadata_json was not valid JSON, reset to {}"}

        merged = dict(existing)
        merged.update(metadata_patch)

        new_meta = json.dumps(merged, ensure_ascii=False)
        now = self._now_iso()
        await self.db.execute(
            "UPDATE memories SET metadata_json=?, updated_at=? WHERE id=?;",
            (new_meta, now, memory_id),
        )
        return True

    async def update_memory_active_state(self, memory_id: str, active_state: str) -> bool:
        """Update active_state with validation — only existing legal values allowed.

        Legal values: active, archived, superseded, quarantined.
        Returns False if state is not legal or memory not found.
        """
        LEGAL = frozenset({"active", "archived", "superseded", "quarantined"})
        if active_state not in LEGAL:
            return False

        now = self._now_iso()
        n = await self.db.execute(
            "UPDATE memories SET active_state=?, updated_at=? WHERE id=?;",
            (active_state, now, memory_id),
        )
        return n > 0

    async def add_conflict(self, memory_id: str, conflicting_memory_id: str, reason: str) -> None:
        now = self._now_iso()
        await self.db.execute("INSERT INTO memory_conflicts(id,memory_id,conflicting_memory_id,contradiction_reason,checksum,resolved_state,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?);",
            (uuid4().hex,memory_id,conflicting_memory_id,reason,self.checksum(f"{memory_id}:{conflicting_memory_id}:{reason}"),"open",now,"{}"))

    async def add_entity(
        self,
        name: str | None = None,
        entity_name: str | None = None,
        entity_type: str = "unknown",
        metadata_json: str = "{}",
    ) -> str:
        # backward-compatible alias
        if name is None:
            name = entity_name or ""
        eid = uuid4().hex
        now = self._now_iso()
        nn = name.lower().strip()
        await self.db.execute("INSERT INTO entities(id,name,entity_type,normalized_name,active_state,checksum,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?);",
            (eid,name,entity_type,nn,"active",self.checksum(f"{nn}:{entity_type}"),now,metadata_json))
        return eid

    async def add_relation(self, source_entity_id: str, target_entity_id: str, relation_type: str, confidence_score: float=1.0) -> str:
        rid = uuid4().hex
        now = self._now_iso()
        await self.db.execute("INSERT INTO relations(id,source_entity_id,target_entity_id,relation_type,confidence_score,active_state,checksum,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?);",
            (rid,source_entity_id,target_entity_id,relation_type,confidence_score,"active",self.checksum(f"{source_entity_id}:{target_entity_id}:{relation_type}"),now,"{}"))
        return rid

    async def add_session_summary(self, session_id: str, summary: str, source_count: int=0) -> None:
        now = self._now_iso()
        ch = self.checksum(summary)
        await self.db.execute("INSERT INTO session_summaries(id,session_id,summary,content_hash,checksum,valid_from,active_state,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?);",
            (uuid4().hex,session_id,summary,ch,ch,now,"active",now,"{}"))

    async def add_episodic_memory(
        self,
        memory_id: str | None = None,
        session_id: str | None = None,
        content: str = "",
        title: str | None = None,
        summary: str | None = None,
        importance_score: float = 0.5,
    ) -> str:
        # backward-compatible alias: title → content, title → summary
        if title is not None:
            if not content:
                content = title
            if summary is None:
                summary = title
        eid = uuid4().hex
        now = self._now_iso()
        ch = self.checksum(content)
        if not memory_id:
            memory_id = f"ep-{eid}"
            # Ensure parent row exists for FK constraint
            await self.db.execute(
                "INSERT OR IGNORE INTO memories(id,memory_type,content,content_hash,checksum,active_state) VALUES (?,?,?,?,?,?);",
                (memory_id, "EPISODE", content, ch, ch, "active"))
        await self.db.execute("INSERT INTO episodic_memories(id,memory_id,session_id,content,summary,importance_score,valid_from,active_state,checksum,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?);",
            (eid,memory_id,session_id,content,summary,importance_score,now,"active",ch,now,"{}"))
        return eid

    async def quarantine_memory(self, memory_id: str, reason: str) -> None:
        now = self._now_iso()
        await self.db.execute("INSERT INTO safety_quarantine(id,memory_id,reason,active_state,checksum,created_at,metadata_json) VALUES (?,?,?,?,?,?,?);",
            (uuid4().hex,memory_id,reason,"quarantined",self.checksum(f"quarantine:{memory_id}:{reason}"),now,"{}"))
        await self.db.execute("UPDATE memories SET active_state='quarantined', updated_at=? WHERE id=?;", (now, memory_id))

    async def append_audit(self, entity_type: str, entity_id: str, action: str, before_json: dict|None=None, after_json: dict|None=None, actor: str|None=None) -> None:
        now = self._now_iso()
        await self.db.execute("INSERT INTO audit_logs(id,entity_type,entity_id,action,before_json,after_json,checksum,created_at,actor,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?);",
            (uuid4().hex,entity_type,entity_id,action,
             json.dumps(before_json) if before_json else None,
             json.dumps(after_json) if after_json else None,
             self.checksum(f"{entity_type}:{entity_id}:{action}:{now}"),now,actor,"{}"))

    async def replay_events(self, action: str|None=None, limit: int=100) -> list[dict[str,Any]]:
        if action:
            rows = await self.db.fetchall("SELECT * FROM audit_logs WHERE action=? ORDER BY created_at ASC LIMIT ?;",(action,limit))
        else:
            rows = await self.db.fetchall("SELECT * FROM audit_logs ORDER BY created_at ASC LIMIT ?;",(limit,))
        return [self._row_to_dict(r) for r in rows]

    async def export_markdown(self, output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        rows = await self.db.fetchall("SELECT * FROM memories ORDER BY updated_at DESC;")
        path = output_dir / "memories.md"
        lines = ["# Memories",""]
        for r in rows:
            item = dict(r)
            lines.append(f"- {item['id']} [{item['memory_type']}] {item['content']}")
        await asyncio.to_thread(path.write_text,"\n".join(lines)+"\n",encoding="utf-8")
        return [path]

    async def rollback_memory(self, memory_id: str) -> None:
        now = self._now_iso()
        await self.db.execute("UPDATE memories SET active_state='archived',valid_to=?,updated_at=? WHERE id=?;",(now,now,memory_id))
        await self.append_audit("memories",memory_id,"rollback_memory")

    async def update_memory_versioned(
        self, memory_id: str, changes: dict[str, Any], *, actor: str = "system", reason: str = ""
    ) -> str:
        """Version-preserving memory update. Writes version + audit atomically."""
        ALLOWED = {
            "content", "importance_score", "confidence_score", "decay_score",
            "recency_score", "active_state", "valid_from", "valid_to", "scope",
            "session_id", "entities_json", "tags_json", "metadata_json",
        }
        safe = {k: v for k, v in changes.items() if k in ALLOWED and k != "id"}
        if not safe:
            return memory_id

        async with self.db.transaction() as conn:
            if "content" in safe:
                safe["checksum"] = self.checksum(str(safe["content"]))
                safe["content_hash"] = safe["checksum"]
            safe["updated_at"] = self._now_iso()

            set_sql = ", ".join(f"{k}=?" for k in safe)
            conn.execute(f"UPDATE memories SET {set_sql} WHERE id=?;", (*safe.values(), memory_id))  # nosec B608

            row = conn.execute("SELECT content, checksum FROM memories WHERE id=?;", (memory_id,)).fetchone()
            if row is None:
                raise KeyError(f"memory not found: {memory_id}")
            content_val = row["content"]
            checksum_val = row["checksum"]

            cur = conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM memory_versions WHERE memory_id=?;", (memory_id,))
            next_ver = int(cur.fetchone()[0])
            now = self._now_iso()
            conn.execute(
                "INSERT INTO memory_versions(id,memory_id,version,content,content_hash,checksum,valid_from,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?);",
                (uuid4().hex, memory_id, next_ver, content_val, checksum_val, checksum_val, now, now, "{}"),
            )

            conn.execute(
                "INSERT INTO audit_logs(id,entity_type,entity_id,action,before_json,after_json,checksum,created_at,actor,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?);",
                (uuid4().hex, "memories", memory_id, "update_versioned", None,
                 json.dumps({"changed": list(safe), "reason": reason}),
                 self.checksum(f"update:{memory_id}:{now}"), now, actor, "{}"),
            )

        return memory_id

