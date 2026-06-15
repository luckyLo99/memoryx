from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import sqlite3
import uuid
from typing import Any

def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def fingerprint(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class RequestLease:
    request_id: str
    session_id: str
    task_fingerprint: str
    status: str

class ActiveRequestStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            self.ensure_schema(con)
    def ensure_schema(self, con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS memoryx_active_requests (
            request_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL,
            superseded_by TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_memoryx_active_requests_session_status
        ON memoryx_active_requests(session_id, status);
        """)
        con.commit()
    def begin_request(self, *, session_id: str | None, task_text: str, request_id: str | None = None) -> RequestLease:
        sid = session_id or "default"
        rid = request_id or uuid.uuid4().hex
        fp = fingerprint(task_text)
        now = utc_iso()
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            self.ensure_schema(con)
            con.execute("UPDATE memoryx_active_requests SET status = 'superseded', superseded_by = ?, updated_at = ? WHERE session_id = ? AND status = 'running'", (rid, now, sid))
            con.execute("INSERT INTO memoryx_active_requests(request_id, session_id, task_fingerprint, status, created_at, updated_at) VALUES (?, ?, ?, 'running', ?, ?)", (rid, sid, fp, now, now))
            con.commit()
        return RequestLease(request_id=rid, session_id=sid, task_fingerprint=fp, status="running")
    def complete_request(self, request_id: str, status: str = "completed") -> None:
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            self.ensure_schema(con)
            con.execute("UPDATE memoryx_active_requests SET status = ?, updated_at = ? WHERE request_id = ? AND status = 'running'", (status, utc_iso(), request_id))
            con.commit()
    def is_current(self, request_id: str, session_id: str | None) -> bool:
        sid = session_id or "default"
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            self.ensure_schema(con)
            row = con.execute("SELECT request_id, status FROM memoryx_active_requests WHERE session_id = ? AND status = 'running' ORDER BY created_at DESC LIMIT 1", (sid,)).fetchone()
            return bool(row and row["request_id"] == request_id and row["status"] == "running")
    def reject_if_stale(self, request_id: str, session_id: str | None) -> dict[str, Any] | None:
        if self.is_current(request_id, session_id):
            return None
        return {"ok": False, "error": "stale_result", "request_id": request_id, "session_id": session_id or "default", "message": "This result belongs to an older superseded request and must not be injected."}