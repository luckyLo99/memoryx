from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import sqlite3
from typing import Any

from .tokens import TokenEstimator


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    summary: str
    source_hash: str
    updated_at: str
    turn_count: int


class SessionSummaryStore:
    """
    Stores compact per-session summaries.
    This prevents raw session_history from being injected by default.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(db_path) as con:
            self.ensure_schema(con)

    def ensure_schema(self, con: sqlite3.Connection) -> None:
        con.execute("""
        CREATE TABLE IF NOT EXISTS memoryx_session_summaries (
            session_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            turn_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        con.commit()

    def get(self, session_id: str | None) -> SessionSummary | None:
        if not session_id:
            return None
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            self.ensure_schema(con)
            row = con.execute(
                "SELECT session_id, summary, source_hash, updated_at, turn_count "
                "FROM memoryx_session_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if not row:
            return None
        return SessionSummary(
            session_id=row["session_id"],
            summary=row["summary"],
            source_hash=row["source_hash"],
            updated_at=row["updated_at"],
            turn_count=int(row["turn_count"]),
        )

    def upsert_from_history(
        self,
        session_id: str,
        session_history: list[str],
        max_summary_tokens: int = 512,
    ) -> SessionSummary:
        estimator = TokenEstimator()
        clean = [x.strip() for x in session_history if x and x.strip()]
        source = "\n".join(clean)
        source_hash = hash_text(source)

        existing = self.get(session_id)
        if existing and existing.source_hash == source_hash:
            return existing

        summary = deterministic_session_summary(clean)
        summary = estimator.truncate_to_tokens(summary, max_summary_tokens)

        result = SessionSummary(
            session_id=session_id,
            summary=summary,
            source_hash=source_hash,
            updated_at=utc_iso(),
            turn_count=len(clean),
        )

        with sqlite3.connect(self.db_path) as con:
            self.ensure_schema(con)
            con.execute(
                "INSERT INTO memoryx_session_summaries(session_id, summary, source_hash, turn_count, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "summary = excluded.summary, source_hash = excluded.source_hash, "
                "turn_count = excluded.turn_count, updated_at = excluded.updated_at",
                (result.session_id, result.summary, result.source_hash,
                 result.turn_count, result.updated_at),
            )
            con.commit()

        return result


def deterministic_session_summary(turns: list[str]) -> str:
    if not turns:
        return ""

    important = []
    for t in turns:
        lowered = t.lower()
        if any(k in lowered for k in ["todo", "decision", "决定", "任务",
                                       "phase", "error", "bug", "fix", "patch"]):
            important.append(t)

    first = turns[:2]
    last = turns[-4:]
    selected = []
    for item in first + important + last:
        if item not in selected:
            selected.append(item)

    lines = ["Session summary:"]
    for item in selected:
        lines.append("- " + item)

    return "\n".join(lines)
