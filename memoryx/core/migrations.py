from __future__ import annotations

import sqlite3


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def add_column_if_missing(
    con: sqlite3.Connection, table: str, column: str, ddl: str
) -> None:
    if table_exists(con, table) and not column_exists(con, table, column):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def apply_phase2_migrations(con: sqlite3.Connection) -> None:
    add_column_if_missing(con, "claims", "decay_score", "decay_score REAL NOT NULL DEFAULT 1.0")
    add_column_if_missing(con, "claims", "access_count", "access_count INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing(con, "claims", "last_accessed_at", "last_accessed_at TEXT")
    add_column_if_missing(con, "claims", "contradiction_group_id", "contradiction_group_id TEXT")
    add_column_if_missing(con, "claims", "superseded_by", "superseded_by TEXT")
    add_column_if_missing(con, "claims", "source_evidence_ids", "source_evidence_ids TEXT")
    add_column_if_missing(con, "claims", "scope", "scope TEXT NOT NULL DEFAULT 'user'")

    con.execute("""
    CREATE TABLE IF NOT EXISTS claim_edges (
        edge_id TEXT PRIMARY KEY,
        from_claim_id TEXT NOT NULL,
        to_claim_id TEXT NOT NULL,
        edge_type TEXT NOT NULL,
        reason TEXT,
        evidence_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS retrieval_events (
        retrieval_id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        claim_id TEXT NOT NULL,
        rank INTEGER NOT NULL,
        final_score REAL NOT NULL,
        confidence_label TEXT NOT NULL,
        retriever TEXT NOT NULL,
        explanation_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS vector_index_meta (
        claim_id TEXT PRIMARY KEY,
        embedding_model TEXT,
        embedding_dim INTEGER,
        vector_ref TEXT,
        vector_hash TEXT,
        indexed_at TEXT
    )
    """)

    con.commit()
