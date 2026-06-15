from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from typing import Any
def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class RuntimeTaskLease:
    task_id: str
    request_id: str
    status: str

class RuntimeTaskGuard:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(db_path) as con:
            self.ensure_schema(con)
    def ensure_schema(self, con: sqlite3.Connection) -> None:
        con.execute("""CREATE TABLE IF NOT EXISTS memoryx_runtime_active_tasks (task_id TEXT NOT NULL, request_id TEXT PRIMARY KEY, status TEXT NOT NULL, superseded_by TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_memx_rt_active_tasks_task_status ON memoryx_runtime_active_tasks(task_id, status)")
        con.commit()
    def begin(self, task_id: str, request_id: str) -> RuntimeTaskLease:
        now = utc_iso()
        with sqlite3.connect(self.db_path) as con:
            self.ensure_schema(con)
            con.execute("UPDATE memoryx_runtime_active_tasks SET status='superseded', superseded_by=?, updated_at=? WHERE task_id=? AND status='running'", (request_id, now, task_id))
            con.execute("INSERT OR REPLACE INTO memoryx_runtime_active_tasks(task_id, request_id, status, created_at, updated_at) VALUES (?,?,'running',?,?)", (task_id, request_id, now, now))
            con.commit()
        return RuntimeTaskLease(task_id=task_id, request_id=request_id, status="running")
    def complete(self, request_id: str) -> None:
        with sqlite3.connect(self.db_path) as con:
            self.ensure_schema(con)
            con.execute("UPDATE memoryx_runtime_active_tasks SET status='completed', updated_at=? WHERE request_id=? AND status='running'", (utc_iso(), request_id))
            con.commit()
    def reject_if_stale(self, task_id: str, request_id: str) -> dict[str, Any] | None:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute("SELECT request_id FROM memoryx_runtime_active_tasks WHERE task_id=? AND status='running' ORDER BY created_at DESC LIMIT 1", (task_id,)).fetchone()
        finally:
            con.close()
        if row and row["request_id"] == request_id:
            return None
        return {"ok": False, "error": "stale_runtime_result", "task_id": task_id, "request_id": request_id, "message": "This runtime result belongs to an older superseded task request."}
