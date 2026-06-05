from __future__ import annotations
from dataclasses import dataclass
import json, sqlite3
from typing import Any

@dataclass(frozen=True)
class ContextPackDiff:
    previous_pack_id: str | None; current_pack_id: str; repeated_item_ids: list[str]; new_item_ids: list[str]; omitted_repeated_item_ids: list[str]

class ContextPackHistory:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(db_path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS memoryx_context_packs (pack_id TEXT PRIMARY KEY, session_id TEXT, request_id TEXT NOT NULL, query TEXT NOT NULL, item_ids_json TEXT NOT NULL, used_tokens INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_memoryx_context_packs_session_created ON memoryx_context_packs(session_id, created_at)")
            con.commit()

    def get_item_ids(self, pack_id: str | None) -> list[str]:
        if not pack_id: return []
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT item_ids_json FROM memoryx_context_packs WHERE pack_id = ?", (pack_id,)).fetchone()
        return list(json.loads(row["item_ids_json"])) if row else []

    def record_pack(self, *, pack_id: str, session_id: str | None, request_id: str, query: str, item_ids: list[str], used_tokens: int):
        with sqlite3.connect(self.db_path) as con:
            con.execute("INSERT OR REPLACE INTO memoryx_context_packs(pack_id, session_id, request_id, query, item_ids_json, used_tokens) VALUES (?, ?, ?, ?, ?, ?)", (pack_id, session_id, request_id, query, json.dumps(item_ids), int(used_tokens)))
            con.commit()

    def diff(self, previous_pack_id: str | None, current_item_ids: list[str], current_pack_id: str) -> ContextPackDiff:
        prev = set(self.get_item_ids(previous_pack_id)); cur = set(current_item_ids)
        return ContextPackDiff(previous_pack_id, current_pack_id, sorted(prev & cur), sorted(cur - prev), [])
