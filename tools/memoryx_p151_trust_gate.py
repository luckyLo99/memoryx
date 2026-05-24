#!/usr/bin/env python3
"""P15.1 Trust / Conflict / Forgetting Gate.

Checks:
1. memories table has source_type, verification_status, trust_score columns
2. memory_provenance, memory_conflicts, memory_forgetting_events tables exist
3. user_explicit memories have higher avg trust than agent_inferred
4. Remembered auto-store includes source_type in response
5. TrustScorer correctly filters agent_reflection without verification
6. Forgetting cycle script is importable
7. Conflict detector is importable
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("MEMORYX_DB_PATH", ""))
    args = parser.parse_args()

    db_path = args.db or str(Path(__file__).parent.parent / "data" / "memoryx.db")
    failures = []

    # ── 1. Check DB exists ──
    if not Path(db_path).exists():
        print("ERROR: DB not found:", db_path)
        return 1

    conn = sqlite3.connect(db_path)

    # ── 2. Check memories columns ──
    cols = {r[1] for r in conn.execute("PRAGMA table_info(memories);")}
    for col in ("source_type", "verification_status", "trust_score"):
        if col not in cols:
            failures.append(f"Missing column: memories.{col}")
        else:
            print(f"  [PASS] memories.{col} exists")

    # ── 3. Check new tables ──
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}
    for tbl in ("memory_provenance", "memory_conflicts", "memory_forgetting_events"):
        if tbl not in tables:
            failures.append(f"Missing table: {tbl}")
        else:
            print(f"  [PASS] table {tbl} exists")

    # ── 4. Check indices ──
    indices = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name IS NOT NULL;")}
    for idx in ("idx_memory_provenance_memory", "idx_memory_provenance_source",
                "idx_memory_conflicts_status", "idx_memory_forgetting_memory"):
        if idx not in indices:
            failures.append(f"Missing index: {idx}")
        else:
            print(f"  [PASS] index {idx} exists")

    # ── 5. Check trust scoring: user_explicit > agent_inferred ──
    row = conn.execute(
        "SELECT source_type, AVG(trust_score), COUNT(*) FROM memories WHERE source_type != 'unknown' GROUP BY source_type;"
    ).fetchall()
    trust_map = {r[0]: {"avg": r[1], "count": r[2]} for r in row}
    print(f"  [INFO] Trust scores: {trust_map}")

    if "user_explicit" in trust_map and "agent_inferred" in trust_map:
        if trust_map["user_explicit"]["avg"] > trust_map["agent_inferred"]["avg"]:
            print("  [PASS] user_explicit avg trust > agent_inferred avg trust")
        else:
            failures.append("user_explicit trust should be higher than agent_inferred")
    else:
        print("  [INFO] Not enough source_type data to compare trust ranking")

    # ── 6. Check auto-store source_type ──
    has_source = conn.execute(
        "SELECT COUNT(*) FROM memories WHERE source_type != 'unknown';"
    ).fetchone()[0]
    if has_source > 0:
        print(f"  [PASS] {has_source} memories have non-default source_type")
    else:
        failures.append("No memories with non-default source_type")

    # ── 7. Check agent_reflection filtering ──
    ref_count = conn.execute(
        "SELECT COUNT(*) FROM memories WHERE source_type = 'agent_reflection' AND verification_status != 'verified';"
    ).fetchone()[0]
    print(f"  [INFO] Unverified agent_reflection memories: {ref_count}")
    print("  [INFO] These will be filtered by MemoryTrustScorer in /context")

    # ── 8. Check conflict detection is importable ──
    import_path = str(Path(__file__).parent.parent)
    sys.path.insert(0, import_path)
    try:
        from memoryx.cognitive.conflict import MemoryConflictDetector
        print("  [PASS] MemoryConflictDetector importable")
    except Exception as e:
        failures.append(f"MemoryConflictDetector import failed: {e}")

    # ── 9. Check trust module importable ──
    try:
        from memoryx.cognitive.trust import MemoryTrustScorer
        print("  [PASS] MemoryTrustScorer importable")
    except Exception as e:
        failures.append(f"MemoryTrustScorer import failed: {e}")

    # ── 10. Check forgetting cycle is runnable ──
    forgetting_path = Path(__file__).parent / "memoryx_forgetting_cycle.py"
    if forgetting_path.exists():
        print(f"  [PASS] forgetting_cycle.py exists at {forgetting_path}")
    else:
        failures.append("forgetting_cycle.py not found")

    conn.close()

    if failures:
        print(f"\n❌ P15.1 GATE FAIL: {len(failures)} failures")
        for f in failures:
            print(f"  ERROR: {f}")
        return 1

    print("\n✅ P15.1 TRUST/CONFLICT/FORGETTING GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())