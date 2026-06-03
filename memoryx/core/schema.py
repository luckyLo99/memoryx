"""Memory Kernel schema — evidence_events / claims / claim_versions / fts_memories."""

import sqlite3

SCHEMA_STMTS = [
    # ---------------------------------------------------------------------------
    # evidence_events — append-only event sourcing for all raw inputs
    # ---------------------------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS evidence_events (
        evidence_id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL,
        session_id TEXT,
        agent_id TEXT,
        user_id TEXT,
        content TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        metadata_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );""",
    # ---------------------------------------------------------------------------
    # claims — current active memory nodes
    # ---------------------------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS claims (
        claim_id TEXT PRIMARY KEY,
        claim_type TEXT NOT NULL,
        content TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('active','superseded','revoked')),
        confidence REAL NOT NULL DEFAULT 0.5,
        importance REAL NOT NULL DEFAULT 0.5,
        valid_from TEXT,
        valid_to TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );""",
    # ---------------------------------------------------------------------------
    # claim_versions — immutable audit trail for every state change
    # ---------------------------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS claim_versions (
        version_id TEXT PRIMARY KEY,
        claim_id TEXT NOT NULL,
        evidence_ids TEXT,
        operation TEXT NOT NULL,
        before_json TEXT,
        after_json TEXT,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );""",
    # ---------------------------------------------------------------------------
    # fts_memories — FTS5 full-text search index over claims
    # ---------------------------------------------------------------------------
    """CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories USING fts5(
        claim_id,
        content
    );""",
]


def apply_schema(conn: sqlite3.Connection) -> None:
    """Execute all DDL statements on the given connection."""
    cur = conn.cursor()
    for stmt in SCHEMA_STMTS:
        cur.execute(stmt)
    conn.commit()
