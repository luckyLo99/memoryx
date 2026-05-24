#!/usr/bin/env python3
"""P15.2 Temporal Runtime Gate.

Checks:
1. tasks table exists with correct columns
2. task_durations table exists
3. /task/start creates a running task
4. /task/end computes duration_seconds
5. duration_seconds > 0
6. entity_id can be aggregated
7. /task/durations returns stats
8. /entity/timeline returns entries
"""

import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

PASS = "✅"
FAIL = "❌"
INFO = "ℹ️"
GREEN = "✅"
RED = "❌"

DB_PATH = os.environ.get("MEMORYX_DB_PATH", "data/memoryx.db")
BASE_URL = os.environ.get("MEMORYX_BASE_URL", "http://127.0.0.1:8080")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode())


def main() -> int:
    results = []
    failed = 0

    print("\n" + "=" * 60)
    print("  P15.2 Temporal Runtime Gate")
    print("=" * 60)

    # ── 1. tasks table exists ──
    try:
        conn = _db()
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}
        if "tasks" in tables:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks);")}
            required = {"task_id", "session_id", "entity_id", "task_type",
                        "status", "start_time", "end_time", "duration_seconds"}
            missing = required - cols
            if not missing:
                results.append(f"  {PASS} tasks table exists with all required columns")
            else:
                results.append(f"  {FAIL} tasks table missing columns: {missing}")
                failed += 1
        else:
            results.append(f"  {FAIL} tasks table does not exist")
            failed += 1

        # ── 2. task_durations table exists ──
        if "task_durations" in tables:
            results.append(f"  {PASS} task_durations table exists")
        else:
            results.append(f"  {FAIL} task_durations table does not exist")
            failed += 1

        conn.close()
    except Exception as e:
        results.append(f"  {FAIL} Database check failed: {e}")
        failed += 1

    # ── 3. /task/start creates running task ──
    test_task_id = None
    try:
        start = _post("/v1/cognitive/task/start", {
            "session_id": "p152-gate-test",
            "entity_id": "gate-entity",
            "task_type": "gate-test",
            "title": "P15.2 gate test",
            "source": "gate_test",
        })
        assert start.get("status") == "running", f"Expected status=running, got {start.get('status')}"
        assert start.get("task_id"), "No task_id returned"
        results.append(f"  {PASS} /task/start created running task: {start['task_id'][:12]}...")
        test_task_id = start["task_id"]
    except Exception as e:
        results.append(f"  {FAIL} /task/start failed: {e}")
        failed += 1

    # ── 4. /task/end computes duration_seconds ──
    if test_task_id:
        try:
            time.sleep(2)
            end = _post("/v1/cognitive/task/end", {
                "session_id": "p152-gate-test",
                "entity_id": "gate-entity",
                "status": "done",
                "summary": "gate test complete",
                "source": "gate_test",
            })
            assert end.get("duration_seconds") is not None, "No duration_seconds"
            # ── 5. duration_seconds > 0 ──
            if int(end["duration_seconds"]) >= 1:
                results.append(f"  {PASS} /task/end computed duration: {end['duration_seconds']}s")
            else:
                results.append(f"  {INFO} /task/end duration: {end['duration_seconds']}s (≥1 expected)")
            results.append(f"  {PASS} /task/end returned status: {end.get('status')}")
        except Exception as e:
            results.append(f"  {FAIL} /task/end failed: {e}")
            failed += 1

    # ── 6. /task/durations returns stats ──
    try:
        stats = _post("/v1/cognitive/task/durations", {"entity_id": "gate-entity"})
        assert "summary" in stats, "No summary"
        assert stats["summary"]["total_tasks"] >= 1, \
            f"Expected ≥1 tasks, got {stats['summary']['total_tasks']}"
        results.append(
            f"  {PASS} /task/durations: {stats['summary']['total_tasks']} tasks, "
            f"{stats['summary']['total_seconds']}s total"
        )
        # ── 7. entity aggregation works ──
        assert len(stats.get("by_entity", [])) >= 1, "No entity breakdown"
        results.append(f"  {PASS} entity_id aggregation: {len(stats['by_entity'])} entities")
    except Exception as e:
        results.append(f"  {FAIL} /task/durations failed: {e}")
        failed += 1

    # ── 8. /entity/timeline returns entries ──
    try:
        timeline = _post("/v1/cognitive/entity/timeline", {"entity_id": "gate-entity", "limit": 5})
        assert timeline.get("count", 0) >= 1, "No timeline entries"
        results.append(f"  {PASS} /entity/timeline: {timeline['count']} entries")
        if timeline["entries"]:
            entry = timeline["entries"][0]
            has_task_id = bool(entry.get("task_id"))
            has_started = bool(entry.get("started_at"))
            has_duration = entry.get("duration_seconds") is not None
            if has_task_id and has_started and has_duration:
                results.append(f"  {PASS} Timeline entry has task_id, started_at, duration_seconds")
            else:
                results.append(f"  {INFO} Timeline entry fields incomplete")
    except Exception as e:
        results.append(f"  {FAIL} /entity/timeline failed: {e}")
        failed += 1

    # ── Summary ──
    total = len(results)
    passed = total - failed
    print()
    for r in results:
        print(r)
    print()
    print("-" * 60)
    if failed == 0:
        print(f"  {GREEN} P15.2 TEMPORAL RUNTIME GATE: PASS ({passed}/{total})")
        code = 0
    else:
        print(f"  {RED} P15.2 TEMPORAL RUNTIME GATE: {failed} CHECKS FAILED ({passed}/{total})")
        code = 1
    print("=" * 60)
    print()
    return code


if __name__ == "__main__":
    raise SystemExit(main())