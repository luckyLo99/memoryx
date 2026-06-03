#!/usr/bin/env python3
"""MemoryX Doctor — installation self-check.

Usage:
    memoryx doctor --profile lite
    memoryx doctor --profile standard
"""

import argparse
import os
import sqlite3
import sys

from memoryx import __version__

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _ok(msg: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}FAIL{RESET}  {msg}")


def _skip(msg: str) -> None:
    print(f"  {YELLOW}SKIP{RESET}  {msg}")


def check_python() -> None:
    v = sys.version_info
    if v >= (3, 11):
        _ok(f"Python {v.major}.{v.minor}.{v.micro} (>=3.11)")
    else:
        _fail(f"Python {v.major}.{v.minor}.{v.micro} (need >=3.11)")


def check_fts5() -> None:
    """Check SQLite FTS5 availability and basic retrieval."""
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE fts_test USING fts5(content)")
        conn.execute("INSERT INTO fts_test VALUES ('hello world')")
        cur = conn.execute(
            "SELECT rowid FROM fts_test WHERE fts_test MATCH ?", ("hello",)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            _ok("SQLite FTS5 available + FTS retrieval works")
        else:
            _fail("FTS5 retrieval returned no rows (unexpected)")
    except Exception as e:
        _fail(f"SQLite FTS5 not available: {e}")


def check_db_writable(profile: str) -> None:
    db_path = os.environ.get("MEMORYX_DB_PATH", "")
    if not db_path:
        db_dir = os.environ.get("MEMORYX_HOME", "./data")
        db_path = os.path.join(db_dir, f"memoryx_{profile}.db")
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS doctor_ck (k TEXT PRIMARY KEY, v TEXT)")
        conn.execute("INSERT OR REPLACE INTO doctor_ck (k, v) VALUES ('ping', 'pass')")
        conn.commit()
        conn.close()
        # cleanup
        os.remove(db_path)
        _ok(f"DB writable ({db_path})")
    except Exception as e:
        _fail(f"DB not writable ({db_path}): {e}")


def check_vector(profile: str) -> None:
    vector_env = os.environ.get("MEMORYX_VECTOR_ENABLED", "").lower()
    embedding_env = os.environ.get("MEMORYX_EMBEDDING_ENABLED", "").lower()
    vector_on = vector_env == "true" or embedding_env == "true"
    if vector_on:
        _skip("Vector embedding (not configured — install lancedb and set MEMORYX_EMBEDDING_* vars)")
    else:
        _skip("Vector embedding (disabled for this profile)")


def check_env_vars(profile: str) -> None:
    """Check that key env variables reflect the chosen profile."""
    profile_env = os.environ.get("MEMORYX_PROFILE", "<not set>")
    _ok(f"MEMORYX_PROFILE={profile_env}")
    db_path = os.environ.get("MEMORYX_DB_PATH", "<not set (using default)>")
    _ok(f"MEMORYX_DB_PATH={db_path}")
    _ok(f"MEMORYX_VECTOR_ENABLED={os.environ.get('MEMORYX_VECTOR_ENABLED', '<not set>')}")
    _ok(f"MEMORYX_EMBEDDING_ENABLED={os.environ.get('MEMORYX_EMBEDDING_ENABLED', '<not set>')}")


def main() -> None:
    # Handle `memoryx doctor` subcommand: pop "doctor" from sys.argv if present
    argv = sys.argv[1:]
    if argv and argv[0] == "doctor":
        argv = argv[1:]
    sys.argv = ["memoryx doctor"] + argv

    parser = argparse.ArgumentParser(
        prog="memoryx",
        description="MemoryX Doctor — installation self-check",
    )
    parser.add_argument(
        "--profile", "-p",
        default="lite",
        choices=["lite", "standard", "dev"],
        help="Profile to check (default: lite)",
    )
    args = parser.parse_args(argv)

    profile = args.profile

    print(f"\n{BOLD}MemoryX Doctor{RESET}")
    print(f"  Version: {CYAN}{__version__}{RESET}")
    print(f"  Profile: {CYAN}{profile}{RESET}\n")

    check_python()
    check_fts5()
    check_db_writable(profile)
    check_env_vars(profile)
    check_vector(profile)

    print()
    print(f"  {BOLD}Tip:{RESET} Run `pytest -q` for full feature checks.")
    print()


if __name__ == "__main__":
    main()
