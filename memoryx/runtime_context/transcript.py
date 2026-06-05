from __future__ import annotations

from dataclasses import dataclass, asdict
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .budget import RuntimeContextBudget
from .truncate import summarize_terminal_output

def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class ToolEvent:
    event_id: str
    task_id: str
    request_id: str
    command: str
    exit_code: int
    duration_ms: float
    stdout_summary: str
    stderr_summary: str
    stdout_truncated: bool
    stderr_truncated: bool
    created_at: str
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class RuntimeTranscriptStore:
    def __init__(self, db_path: str, budget: RuntimeContextBudget | None = None):
        self.db_path = db_path
        self.budget = budget or RuntimeContextBudget.from_env()
        with sqlite3.connect(db_path) as con:
            self.ensure_schema(con)
    def ensure_schema(self, con: sqlite3.Connection) -> None:
        con.execute("""
        CREATE TABLE IF NOT EXISTS memoryx_runtime_tool_events (
            event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, request_id TEXT NOT NULL,
            command TEXT NOT NULL, exit_code INTEGER NOT NULL, duration_ms REAL NOT NULL,
            stdout_summary TEXT NOT NULL, stderr_summary TEXT NOT NULL,
            stdout_truncated INTEGER NOT NULL, stderr_truncated INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_memx_rt_tool_events_task_created ON memoryx_runtime_tool_events(task_id, created_at)")
        con.commit()
    def record_command(self, *, event_id: str, task_id: str, request_id: str, command: str, exit_code: int, duration_ms: float, stdout: str, stderr: str = "") -> ToolEvent:
        summary = summarize_terminal_output(stdout, stderr, max_stdout_chars=self.budget.max_command_stdout_chars, max_stderr_chars=self.budget.max_command_stderr_chars, max_lines=self.budget.max_terminal_lines)
        event = ToolEvent(event_id=event_id, task_id=task_id, request_id=request_id, command=command, exit_code=exit_code, duration_ms=duration_ms, stdout_summary=summary["stdout"], stderr_summary=summary["stderr"], stdout_truncated=summary["stdout_truncated"], stderr_truncated=summary["stderr_truncated"], created_at=utc_iso())
        with sqlite3.connect(self.db_path) as con:
            self.ensure_schema(con)
            con.execute("""INSERT OR REPLACE INTO memoryx_runtime_tool_events(event_id, task_id, request_id, command, exit_code, duration_ms, stdout_summary, stderr_summary, stdout_truncated, stderr_truncated, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (event.event_id, event.task_id, event.request_id, event.command, event.exit_code, event.duration_ms, event.stdout_summary, event.stderr_summary, 1 if event.stdout_truncated else 0, 1 if event.stderr_truncated else 0, event.created_at))
            con.commit()
        return event
    def recent_events(self, task_id: str, limit: int = 12) -> list[ToolEvent]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute("SELECT * FROM memoryx_runtime_tool_events WHERE task_id = ? ORDER BY created_at DESC LIMIT ?", (task_id, limit)).fetchall()
        finally:
            con.close()
        return [ToolEvent(event_id=r["event_id"], task_id=r["task_id"], request_id=r["request_id"], command=r["command"], exit_code=int(r["exit_code"]), duration_ms=float(r["duration_ms"]), stdout_summary=r["stdout_summary"], stderr_summary=r["stderr_summary"], stdout_truncated=bool(r["stdout_truncated"]), stderr_truncated=bool(r["stderr_truncated"]), created_at=r["created_at"]) for r in rows][::-1]
