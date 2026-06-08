from __future__ import annotations

import sqlite3

from .migrations import apply_phase2_migrations

SCHEMA_STMTS = [
    """
    CREATE TABLE IF NOT EXISTS evidence_events (
        evidence_id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL,
        session_id TEXT,
        agent_id TEXT,
        user_id TEXT,
        content TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        metadata_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS claims (
        claim_id TEXT PRIMARY KEY,
        claim_type TEXT NOT NULL,
        content TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        confidence REAL NOT NULL DEFAULT 0.5,
        importance REAL NOT NULL DEFAULT 0.5,
        valid_from TEXT,
        valid_to TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS claim_versions (
        version_id TEXT PRIMARY KEY,
        claim_id TEXT NOT NULL,
        evidence_ids TEXT,
        operation TEXT NOT NULL,
        before_json TEXT,
        after_json TEXT,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories USING fts5(
        claim_id UNINDEXED,
        content
    )
    """,
]


def apply_schema(conn: sqlite3.Connection) -> None:
    for stmt in SCHEMA_STMTS:
        conn.execute(stmt)
    conn.commit()
    apply_phase2_migrations(conn)
