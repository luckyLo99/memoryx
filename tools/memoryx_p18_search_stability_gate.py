#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent.parent
DB = os.getenv("MEMORYX_DB_PATH", str(REPO_DIR / 'data' / 'memoryx.db'))


def fail(msg: str) -> None:
    print("FAIL:", msg)
    raise SystemExit(1)


def ok(msg: str) -> None:
    print("OK:", msg)


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view');")}

    required = {"session_search_index", "session_search_cache"}
    missing = sorted(required - tables)
    if missing:
        fail(f"missing tables: {missing}")
    ok("session search tables exist")

    fts = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}
    if "session_search_fts" not in fts:
        fail("session_search_fts missing")
    ok("session_search_fts exists")

    n = conn.execute("SELECT COUNT(*) AS n FROM session_search_index;").fetchone()["n"]
    if int(n or 0) < 1:
        fail("session_search_index is empty; run maintenance first")
    ok(f"session_search_index has {n} sessions")

    started = time.perf_counter()
    rows = conn.execute(
        """
        SELECT idx.session_id, idx.summary
        FROM session_search_fts
        JOIN session_search_index idx ON idx.session_id=session_search_fts.session_id
        WHERE session_search_fts MATCH ?
        LIMIT 5;
        """,
        ("memoryx OR hermes OR 小红书",),
    ).fetchall()
    elapsed_ms = (time.perf_counter() - started) * 1000

    if elapsed_ms > 50:
        fail(f"session FTS too slow: {elapsed_ms:.2f}ms")
    ok(f"session FTS latency OK: {elapsed_ms:.2f}ms, rows={len(rows)}")

    print("P18 SEARCH STABILITY GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())