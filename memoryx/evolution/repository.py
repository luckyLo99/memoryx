"""Repository for evolution nodes (storage layer)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from .models import EvolutionNode


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memory_evolution (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    slot TEXT NOT NULL,
    value TEXT NOT NULL,
    kind TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    source_memory_id TEXT,
    context TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    active_state TEXT NOT NULL DEFAULT 'active',
    decay_score REAL NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_evo_entity_slot ON memory_evolution(entity_id, slot, valid_from);
CREATE INDEX IF NOT EXISTS idx_evo_active_valid ON memory_evolution(active_state, valid_to);
CREATE INDEX IF NOT EXISTS idx_evo_source ON memory_evolution(source_memory_id);
"""


def ensure_evolution_table(db_path: Path) -> None:
    """Create the memory_evolution table if it doesn't exist.

    Safe to call on every startup. Uses the same SQLite file as MemoryRepository.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


class EvolutionRepository:
    """CRUD for memory_evolution nodes."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        ensure_evolution_table(self.db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_node(self, node: EvolutionNode) -> EvolutionNode:
        """Insert a new node, deactivating the previous active node for the same (entity, slot)."""
        conn = self._conn()
        try:
            # Deactivate previous active node(s) for this (entity, slot) and set valid_to
            prev = conn.execute(
                """
                SELECT id, valid_from FROM memory_evolution
                WHERE entity_id = ? AND slot = ? AND active_state = 'active'
                ORDER BY valid_from DESC
                """,
                (node.entity_id, node.slot),
            ).fetchall()
            if prev:
                for row in prev:
                    # Close out the previous node's validity window
                    conn.execute(
                        "UPDATE memory_evolution SET valid_to = ?, active_state = 'superseded' WHERE id = ? AND valid_to IS NULL",
                        (node.valid_from, row["id"]),
                    )
            conn.execute(
                """
                INSERT INTO memory_evolution (
                    id, entity_id, slot, value, kind, valid_from, valid_to,
                    confidence, source_memory_id, context, created_at, active_state, decay_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.id,
                    node.entity_id,
                    node.slot,
                    node.value,
                    node.kind.value,
                    node.valid_from,
                    node.valid_to,
                    node.confidence,
                    node.source_memory_id,
                    node.context,
                    node.created_at,
                    node.active_state,
                    node.decay_score,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return node

    def get_active(self, entity_id: str, slot: str) -> Optional[EvolutionNode]:
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM memory_evolution
                WHERE entity_id = ? AND slot = ? AND active_state = 'active'
                ORDER BY valid_from DESC LIMIT 1
                """,
                (entity_id, slot),
            ).fetchone()
            if row is None:
                return None
            return EvolutionNode.from_row(dict(row))
        finally:
            conn.close()

    def list_by_entity_slot(
        self, entity_id: str, slot: str, include_inactive: bool = True
    ) -> list[EvolutionNode]:
        conn = self._conn()
        try:
            if include_inactive:
                rows = conn.execute(
                    """
                    SELECT * FROM memory_evolution
                    WHERE entity_id = ? AND slot = ?
                    ORDER BY valid_from ASC
                    """,
                    (entity_id, slot),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM memory_evolution
                    WHERE entity_id = ? AND slot = ? AND active_state = 'active'
                    ORDER BY valid_from ASC
                    """,
                    (entity_id, slot),
                ).fetchall()
            return [EvolutionNode.from_row(dict(r)) for r in rows]
        finally:
            conn.close()

    def list_slots(self, entity_id: str) -> list[str]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT DISTINCT slot FROM memory_evolution WHERE entity_id = ?",
                (entity_id,),
            ).fetchall()
            return [r["slot"] for r in rows]
        finally:
            conn.close()

    def archive_old(self, entity_id: str, slot: str) -> int:
        """Soft-archive old nodes (used by forgetting task). Returns count archived."""
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                UPDATE memory_evolution
                SET active_state = 'archived'
                WHERE entity_id = ? AND slot = ? AND active_state != 'archived'
                """,
                (entity_id, slot),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def update_decay(self, node_id: str, decay_score: float) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE memory_evolution SET decay_score = ? WHERE id = ?",
                (decay_score, node_id),
            )
            conn.commit()
        finally:
            conn.close()
