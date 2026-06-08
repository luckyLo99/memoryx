#!/usr/bin/env python3
"""Safely apply migration 050: add columns + create tables.
Uses PRAGMA table_info() to avoid errors on re-run."""

import os
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4


def add_column_if_missing(conn, table, column, col_type_default):
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table});")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type_default};")
        return True
    return False


def main():
    db_path = os.environ.get("MEMORYX_DB_PATH")
    if not db_path:
        db_path = str(Path(__file__).parent.parent / "data" / "memoryx.db")

    print(f"Applying 050 migration to: {db_path}")

    if not Path(db_path).exists():
        print(f"ERROR: DB not found: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")

    # ── memories columns ──
    cols = [
        ("source_type", "TEXT DEFAULT 'unknown'"),
        ("verification_status", "TEXT DEFAULT 'unverified'"),
        ("expires_at", "TEXT"),
        ("last_verified_at", "TEXT"),
        ("trust_score", "REAL DEFAULT 0.5"),
    ]

    added_cols = 0
    for col_name, col_def in cols:
        if add_column_if_missing(conn, "memories", col_name, col_def):
            print(f"  + Added column: memories.{col_name}")
            added_cols += 1

    # ── new tables ──
    tables_sql = {
        "memory_provenance": """
            CREATE TABLE IF NOT EXISTS memory_provenance (
                id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ref TEXT,
                evidence_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """,
        "memory_conflicts": """
            CREATE TABLE IF NOT EXISTS memory_conflicts (
                id TEXT PRIMARY KEY,
                memory_a_id TEXT NOT NULL,
                memory_b_id TEXT NOT NULL,
                conflict_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                confidence REAL NOT NULL DEFAULT 0.5,
                summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT
            );
        """,
        "memory_forgetting_events": """
            CREATE TABLE IF NOT EXISTS memory_forgetting_events (
                id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                old_confidence REAL,
                new_confidence REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """,
    }

    added_tables = 0
    for table_name, create_sql in tables_sql.items():
        existing = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            )
        }
        if table_name == "memory_conflicts" and table_name in existing:
            # Check if it has the right columns; if not, drop and recreate
            existing_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table_name});")}
            required_cols = {"id", "memory_a_id", "memory_b_id", "conflict_type", "status", "confidence", "summary", "created_at", "resolved_at"}
            if not required_cols.issubset(existing_cols):
                conn.execute(f"DROP TABLE IF EXISTS {table_name};")
                conn.execute("DROP INDEX IF EXISTS idx_memory_conflicts_status;")
                conn.execute(create_sql)
                print(f"  + Recreated table: {table_name} (missing columns)")
                added_tables += 1
                continue
            print(f"  = Already exists: {table_name}")
        elif table_name not in existing:
            conn.execute(create_sql)
            print(f"  + Created table: {table_name}")
            added_tables += 1
        else:
            print(f"  = Already exists: {table_name}")

    # ── indices ──
    indices = {
        "idx_memory_provenance_memory":
            "CREATE INDEX IF NOT EXISTS idx_memory_provenance_memory ON memory_provenance(memory_id);",
        "idx_memory_provenance_source":
            "CREATE INDEX IF NOT EXISTS idx_memory_provenance_source ON memory_provenance(source_type, created_at);",
        "idx_memory_conflicts_status":
            "CREATE INDEX IF NOT EXISTS idx_memory_conflicts_status ON memory_conflicts(status, created_at);",
        "idx_memory_forgetting_memory":
            "CREATE INDEX IF NOT EXISTS idx_memory_forgetting_memory ON memory_forgetting_events(memory_id, created_at);",
    }

    for idx_name, idx_sql in indices.items():
        conn.execute(idx_sql)

    conn.commit()

    # ── update trust_score for existing memories ──
    updated = conn.execute("""
        UPDATE memories
        SET trust_score =
            CASE
                WHEN source_type = 'user_explicit' AND verification_status = 'verified' THEN 0.95
                WHEN source_type = 'user_explicit' THEN 0.85
                WHEN source_type = 'tool_verified' THEN 0.90
                WHEN source_type = 'system_event' THEN 0.85
                WHEN source_type = 'conversation_log' THEN 0.75
                WHEN source_type = 'agent_inferred' THEN 0.45
                WHEN source_type = 'agent_reflection' THEN 0.35
                ELSE 0.40
            END
        WHERE trust_score = 0.5;
    """)
    conn.commit()

    print(f"\n✅ Migration 050 complete")
    print(f"   Columns added: {added_cols}")
    print(f"   Tables created: {added_tables}")
    print(f"   Existing memories trust-scored: {updated.rowcount}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())