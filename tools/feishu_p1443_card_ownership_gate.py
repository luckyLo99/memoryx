#!/usr/bin/env python3
"""P14.4.3 Feishu Card Ownership Gate — 验证卡片所有权修复。

验收标准：
1. latest job: state=done, visible_state=done, phase=done
2. card_message_id 非空
3. revision >= 5（动态 patch 至少 5 次）
4. DLQ = 0
5. trace 包含 card_initial_sent, card_patch_done, job_done
6. feishu_card_messages 表有记录且 outbound_card_message_id 一致
"""
from __future__ import annotations

import os
import sqlite3
import sys


QUEUE_DB = os.getenv("QUEUE_DB", "/home/lucky/memoryx/data/feishu_queue.db")


def fail(msg: str) -> None:
    print("FAIL:", msg)
    raise SystemExit(1)


def ok(msg: str) -> None:
    print("OK:", msg)


def main() -> int:
    conn = sqlite3.connect(QUEUE_DB)
    conn.row_factory = sqlite3.Row

    # 1. 检查最新 job
    row = conn.execute(
        """
        SELECT job_id, state, visible_state, phase, revision, card_message_id, attempts
        FROM feishu_jobs
        ORDER BY created_at DESC
        LIMIT 1;
        """
    ).fetchone()

    if not row:
        fail("no feishu job found")

    latest = dict(row)

    if latest["state"] != "done":
        fail(f"latest job not done: {latest}")

    if latest["visible_state"] != "done":
        fail(f"visible_state not done: {latest}")

    if latest["phase"] != "done":
        fail(f"phase not done: {latest}")

    if not latest["card_message_id"]:
        fail(f"card_message_id empty: {latest}")

    if int(latest["revision"] or 0) < 5:
        fail(f"revision too low; dynamic patch likely not working: {latest}")

    ok("latest job state/visible/phase/card_message_id/revision OK")

    # 2. 检查 DLQ
    dlq = conn.execute(
        "SELECT COUNT(*) AS n FROM feishu_dead_letters;"
    ).fetchone()["n"]
    if int(dlq or 0) != 0:
        fail(f"DLQ not empty: {dlq}")
    ok("DLQ=0")

    # 3. 检查 trace 事件
    events = [
        r["event_type"]
        for r in conn.execute(
            """
            SELECT event_type
            FROM feishu_trace_events
            WHERE job_id=?
            ORDER BY created_at ASC;
            """,
            (latest["job_id"],),
        ).fetchall()
    ]

    required = [
        "event_accepted",
        "job_queued",
        "job_claimed",
        "card_initial_sent",
        "state_transition",
        "card_patch_done",
        "job_done",
    ]

    missing = [x for x in required if x not in events]
    if missing:
        fail(f"missing trace events: {missing}; events={events}")

    patch_count = events.count("card_patch_done")
    if patch_count < 3:
        fail(f"card_patch_done count too low: {patch_count}; events={events}")

    ok(f"trace complete, card_patch_done={patch_count}")

    # 4. 检查 card ownership mapping
    card_row = conn.execute(
        """
        SELECT outbound_card_message_id
        FROM feishu_card_messages
        WHERE job_id=?;
        """,
        (latest["job_id"],),
    ).fetchone()

    if not card_row:
        fail("feishu_card_messages missing latest job record")

    if card_row["outbound_card_message_id"] != latest["card_message_id"]:
        fail("card message ownership mismatch")

    ok("card ownership mapping OK")

    # 5. 检查 card_message_id 列在 feishu_jobs 中
    cols = [c[1] for c in conn.execute("PRAGMA table_info(feishu_jobs)").fetchall()]
    if "card_message_id" not in cols:
        fail("card_message_id column missing from feishu_jobs")

    ok("card_message_id column exists in feishu_jobs")

    print("\nP14.4.3 FEISHU CARD OWNERSHIP GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
