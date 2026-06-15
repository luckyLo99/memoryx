from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any
from .budget import RuntimeContextBudget

def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class TaskCapsule:
    task_id: str
    objective: str
    constraints: list[str]
    completed_steps: list[str]
    current_state: str
    next_steps: list[str]
    updated_at: str
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class TaskCapsuleStore:
    def __init__(self, db_path: str, budget: RuntimeContextBudget | None = None):
        self.db_path = db_path
        self.budget = budget or RuntimeContextBudget.from_env()
        with sqlite3.connect(db_path) as con:
            self.ensure_schema(con)
    def ensure_schema(self, con: sqlite3.Connection) -> None:
        con.execute("""CREATE TABLE IF NOT EXISTS memoryx_runtime_task_capsules (task_id TEXT PRIMARY KEY, objective TEXT NOT NULL, constraints_json TEXT NOT NULL, completed_steps_json TEXT NOT NULL, current_state TEXT NOT NULL, next_steps_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        con.commit()
    def upsert(self, capsule: TaskCapsule) -> TaskCapsule:
        with sqlite3.connect(self.db_path) as con:
            self.ensure_schema(con)
            con.execute("""INSERT OR REPLACE INTO memoryx_runtime_task_capsules(task_id, objective, constraints_json, completed_steps_json, current_state, next_steps_json, updated_at) VALUES (?,?,?,?,?,?,?)""",
                (capsule.task_id, capsule.objective, json.dumps(capsule.constraints, ensure_ascii=False), json.dumps(capsule.completed_steps, ensure_ascii=False), capsule.current_state, json.dumps(capsule.next_steps, ensure_ascii=False), capsule.updated_at))
            con.commit()
        return capsule
    def get(self, task_id: str) -> TaskCapsule | None:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute("SELECT * FROM memoryx_runtime_task_capsules WHERE task_id = ?", (task_id,)).fetchone()
        finally:
            con.close()
        if not row:
            return None
        return TaskCapsule(task_id=row["task_id"], objective=row["objective"], constraints=json.loads(row["constraints_json"]), completed_steps=json.loads(row["completed_steps_json"]), current_state=row["current_state"], next_steps=json.loads(row["next_steps_json"]), updated_at=row["updated_at"])
