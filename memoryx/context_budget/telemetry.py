from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from typing import Any



def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ContextTelemetryRecord:
    pack_id: str
    session_id: str | None
    request_id: str
    mode: str
    used_tokens: int
    included_items: int
    dropped_items: int
    static_prefix_hash: str
    memory_block_hash: str
    dynamic_block_hash: str
    full_pack_hash: str
    estimated_cache_hit: bool
    cache_reuse_ratio: float
    latency_ms: float


class ContextPackTelemetryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(db_path) as con:
            self.ensure_schema(con)

    def ensure_schema(self, con: sqlite3.Connection) -> None:
        con.execute("""
        CREATE TABLE IF NOT EXISTS memoryx_context_pack_telemetry (
            pack_id TEXT PRIMARY KEY,
            session_id TEXT,
            request_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            used_tokens INTEGER NOT NULL,
            included_items INTEGER NOT NULL,
            dropped_items INTEGER NOT NULL,
            static_prefix_hash TEXT NOT NULL,
            memory_block_hash TEXT NOT NULL,
            dynamic_block_hash TEXT NOT NULL,
            full_pack_hash TEXT NOT NULL,
            estimated_cache_hit INTEGER NOT NULL DEFAULT 0,
            cache_reuse_ratio REAL NOT NULL DEFAULT 0,
            latency_ms REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        con.execute("""
        CREATE INDEX IF NOT EXISTS idx_memoryx_context_pack_telemetry_session_created
        ON memoryx_context_pack_telemetry(session_id, created_at)
        """)
        con.commit()

    def last_for_session(self, session_id: str | None) -> dict[str, Any] | None:
        if not session_id:
            return None
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            self.ensure_schema(con)
            row = con.execute(
                """
                SELECT *
                FROM memoryx_context_pack_telemetry
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def estimate_reuse(
        self,
        *,
        session_id: str | None,
        static_prefix_hash: str,
        memory_block_hash: str,
        dynamic_block_hash: str,
    ) -> dict[str, Any]:
        previous = self.last_for_session(session_id)
        if not previous:
            return {
                "estimated_cache_hit": False,
                "cache_reuse_ratio": 0.0,
                "reason": "no_previous_pack",
            }

        static_same = previous["static_prefix_hash"] == static_prefix_hash
        memory_same = previous["memory_block_hash"] == memory_block_hash
        dynamic_same = previous["dynamic_block_hash"] == dynamic_block_hash

        if static_same and memory_same and dynamic_same:
            ratio = 1.0
        elif static_same and memory_same:
            ratio = 0.80
        elif static_same:
            ratio = 0.35
        else:
            ratio = 0.0

        return {
            "estimated_cache_hit": bool(static_same),
            "cache_reuse_ratio": ratio,
            "reason": "static_memory_dynamic_match"
            if ratio == 1.0 else
            "static_memory_match"
            if ratio == 0.80 else
            "static_prefix_match"
            if ratio == 0.35 else
            "no_prefix_match",
            "previous_pack_id": previous["pack_id"],
        }

    def record(self, record: ContextTelemetryRecord) -> None:
        with sqlite3.connect(self.db_path) as con:
            self.ensure_schema(con)
            con.execute(
                """
                INSERT OR REPLACE INTO memoryx_context_pack_telemetry(
                    pack_id, session_id, request_id, mode, used_tokens, included_items,
                    dropped_items, static_prefix_hash, memory_block_hash, dynamic_block_hash,
                    full_pack_hash, estimated_cache_hit, cache_reuse_ratio, latency_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.pack_id,
                    record.session_id,
                    record.request_id,
                    record.mode,
                    record.used_tokens,
                    record.included_items,
                    record.dropped_items,
                    record.static_prefix_hash,
                    record.memory_block_hash,
                    record.dynamic_block_hash,
                    record.full_pack_hash,
                    1 if record.estimated_cache_hit else 0,
                    float(record.cache_reuse_ratio),
                    float(record.latency_ms),
                    utc_iso(),
                ),
            )
            con.commit()
