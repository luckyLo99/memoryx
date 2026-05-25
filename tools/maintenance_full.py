#!/usr/bin/env python3
"""MemoryX 全面维护脚本：会话总结 + 叙事反思 + 衰减 + 强化。

执行顺序：
1. 从 conversation_logs 回填 sessions
2. 为每个会话生成摘要 (session_summaries)
3. 生成叙事反思 (narrative_reflections)
4. 衰减旧记忆 / 强化重要记忆 / 合并重复

用法：
  python tools/maintenance_full.py            # 全面运行
  python tools/maintenance_full.py --dry-run   # 只报告不修改
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any


DB_PATH = os.getenv("MEMORYX_DB_PATH", "/home/lucky/memoryx/data/memoryx.db")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def timestamp_to_dt(ts_str: str) -> datetime:
    if not ts_str:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00").replace(" ", "T"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="MemoryX 全面维护")
    parser.add_argument("--dry-run", action="store_true", help="只报告不修改")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"❌ DB not found: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    dry = args.dry_run
    mode = "DRY-RUN" if dry else "EXECUTE"
    print(f"\n{'='*60}")
    print(f"MemoryX 全面维护 ({mode})")
    print(f"DB: {DB_PATH}")
    print(f"{'='*60}\n")

    # ── 1. 从 conversation_logs 回填 sessions ──
    print("[1/4] 回填 sessions...")

    # 获取所有有会话 ID 的 conversation_logs
    distinct = conn.execute(
        "SELECT DISTINCT session_id, MIN(created_at) AS first_seen, MAX(created_at) AS last_seen "
        "FROM conversation_logs WHERE session_id IS NOT NULL AND session_id != '' "
        "GROUP BY session_id"
    ).fetchall()

    backfilled = 0
    for row in distinct:
        sid = row["session_id"]
        exists = conn.execute("SELECT 1 FROM sessions WHERE session_id=?", (sid,)).fetchone()
        if exists:
            continue  # 已有 session，跳过

        start_ts = row["first_seen"]
        end_ts = row["last_seen"]
        start_dt = timestamp_to_dt(start_ts)
        end_dt = timestamp_to_dt(end_ts)
        duration = max(1, int((end_dt - start_dt).total_seconds()))
        title = f"Session {sid[:16]}"

        if not dry:
            conn.execute(
                "INSERT INTO sessions(session_id, title, start_time, end_time, duration_seconds, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'closed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (sid, title, start_ts, end_ts, duration),
            )
        backfilled += 1

    conn.commit()
    print(f"  ✅ 回填 {backfilled} 个 session (dry={dry})")

    # ── 2. 为每个 session 生成摘要 ──
    print("[2/4] 生成会话摘要...")

    all_sessions = conn.execute(
        "SELECT session_id, start_time, end_time FROM sessions WHERE status='closed' ORDER BY start_time DESC"
    ).fetchall()

    summarized = 0
    for sess in all_sessions:
        sid = sess["session_id"]

        # 检查是否已有摘要
        existing = conn.execute("SELECT 1 FROM session_summaries WHERE session_id=?", (sid,)).fetchone()
        if existing:
            continue

        # 收集这个 session 的对话记录
        logs = conn.execute(
            "SELECT role, content, created_at FROM conversation_logs WHERE session_id=? ORDER BY created_at ASC",
            (sid,),
        ).fetchall()

        if not logs:
            summary = "无对话记录"
            source_count = 0
        else:
            # 提取 user 消息和 assistant 消息
            user_msgs = [l["content"] for l in logs if l["role"] == "user"]
            assistant_msgs = [l["content"] for l in logs if l["role"] == "assistant"]
            topic = user_msgs[0][:100] if user_msgs else "未知主题"
            summary = (
                f"会话摘要：{len(user_msgs)} 条用户消息, {len(assistant_msgs)} 条助手回复。"
                f"主题：{topic}。"
                f"时间：{sess['start_time']} ~ {sess['end_time']}"
            )
            source_count = len(logs)

        if not dry:
            conn.execute(
                "INSERT INTO session_summaries(session_id, summary, source_count, created_at, updated_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (sid, summary, source_count),
            )
        summarized += 1

    conn.commit()
    print(f"  ✅ 生成 {summarized} 个会话摘要 (dry={dry})")

    # ── 3. 生成叙事反思 ──
    print("[3/4] 生成叙事反思...")

    existing_refs = conn.execute("SELECT COUNT(*) FROM narrative_reflections").fetchone()[0]
    print(f"  现有反思: {existing_refs}")

    # 为每个 closed session 生成一次反思
    new_refs = 0
    for sess in all_sessions:
        sid = sess["session_id"]
        # 检查是否已为这个 session 生成过反思
        has_ref = conn.execute(
            "SELECT 1 FROM narrative_reflections WHERE session_id=? AND reflection_type='session'",
            (sid,),
        ).fetchone()
        if has_ref:
            continue

        # 找这个 session 的摘要
        summ = conn.execute(
            "SELECT summary FROM session_summaries WHERE session_id=?",
            (sid,),
        ).fetchone()

        summary_text = summ["summary"] if summ else f"Session {sid[:16]} 的会话记录"
        window_start = sess["start_time"] or "1970-01-01T00:00:00"
        window_end = sess["end_time"] or now_utc()

        # 获取这个 session 的任务耗时
        tasks = conn.execute(
            "SELECT COUNT(*) AS cnt, SUM(duration_seconds) AS total_dur FROM tasks WHERE session_id=?",
            (sid,),
        ).fetchone()

        metrics = {
            "task_count": tasks["cnt"] or 0,
            "total_duration_seconds": tasks["total_dur"] or 0,
            "source_summary_count": 1,
        }

        evidence = [
            {"type": "session_summary", "source": sid, "preview": summary_text[:200]}
        ]

        import uuid
        ref_id = uuid.uuid4().hex
        summary_body = (
            f"时间窗口 {window_start} 到 {window_end} 的认知总结：\n"
            f"会话概要：{summary_text}\n"
            f"任务统计：{metrics['task_count']} 个任务, 总耗时 {metrics['total_duration_seconds']} 秒"
        )

        if not dry:
            conn.execute(
                "INSERT INTO narrative_reflections(id, session_id, window_start, window_end, reflection_type, "
                "summary, evidence_json, metrics_json, created_at) "
                "VALUES (?, ?, ?, ?, 'session', ?, ?, ?, CURRENT_TIMESTAMP)",
                (ref_id, sid, window_start, window_end, summary_body,
                 json.dumps(evidence, ensure_ascii=False),
                 json.dumps(metrics, ensure_ascii=False)),
            )
        new_refs += 1

    # 也生成一个全局的时间段反思
    last_ref = conn.execute(
        "SELECT window_end FROM narrative_reflections ORDER BY window_end DESC LIMIT 1"
    ).fetchone()
    global_start = last_ref["window_end"] if last_ref else "1970-01-01T00:00:00"
    global_end = now_utc()

    has_global = conn.execute(
        "SELECT 1 FROM narrative_reflections WHERE reflection_type='periodic' AND window_end > ?",
        (datetime.now(timezone.utc) - timedelta(hours=2),),
    ).fetchone()

    if not has_global and not dry:
        # 收集近期会话
        recent_sessions = conn.execute(
            "SELECT s.session_id, s.start_time, ss.summary FROM sessions s "
            "LEFT JOIN session_summaries ss ON s.session_id=ss.session_id "
            "WHERE s.end_time > ? ORDER BY s.start_time DESC LIMIT 10",
            (datetime.now(timezone.utc) - timedelta(days=1),),
        ).fetchall()

        session_lines = [f"- {s['session_id'][:16]}: {s['summary'][:100]}" for s in recent_sessions]
        session_text = "\n".join(session_lines) if session_lines else "无近期活跃会话"

        import uuid
        global_id = uuid.uuid4().hex
        global_summary = (
            f"全局时间窗口 {global_start} 到 {global_end} 的认知总结：\n"
            f"近期活跃会话 ({len(recent_sessions)} 个)：\n{session_text}"
        )
        conn.execute(
            "INSERT INTO narrative_reflections(id, window_start, window_end, reflection_type, "
            "summary, evidence_json, metrics_json, created_at) "
            "VALUES (?, ?, ?, 'periodic', ?, '[]', '{}', CURRENT_TIMESTAMP)",
            (global_id, global_start, global_end, global_summary),
        )
        new_refs += 1

    conn.commit()
    print(f"  ✅ 新增 {new_refs} 个叙事反思 (dry={dry})")

    # ── 4. 衰减 + 强化 + 合并 ──
    print("[4/4] 记忆维护...")

    # 衰减：访问少且不重要的记忆
    decayed = 0
    to_decay = conn.execute(
        "SELECT id AS memory_id, access_count, importance_score, decay_score FROM memories "
        "WHERE active_state='active' AND (access_count IS NULL OR access_count <= 1) "
        "AND (importance_score IS NULL OR importance_score < 0.6)"
    ).fetchall()
    for m in to_decay:
        new_decay = min(1.0, (float(m["decay_score"] or 0.0) + 0.15))
        if not dry:
            conn.execute("UPDATE memories SET decay_score=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (new_decay, m["memory_id"]))
        decayed += 1
    print(f"  衰减: {decayed} 条记忆 (dry={dry})")

    # 强化：重要或高频访问的记忆
    reinforced = 0
    to_reinforce = conn.execute(
        "SELECT id AS memory_id, importance_score, access_count, reinforcement_score FROM memories "
        "WHERE active_state='active' AND ("
        "  (importance_score IS NOT NULL AND importance_score >= 0.85) "
        "  OR (access_count IS NOT NULL AND access_count >= 3)"
        ")"
    ).fetchall()
    import uuid
    for m in to_reinforce:
        new_score = min(1.0, (float(m["reinforcement_score"] or 0.0) + 0.15))
        if not dry:
            conn.execute("UPDATE memories SET reinforcement_score=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (new_score, m["memory_id"]))
            conn.execute(
                "INSERT INTO reinforcement_events(reinforcement_id, memory_id, reinforcement_type, score_delta, created_at) "
                "VALUES (?, ?, 'consolidation_reinforcement', 0.15, CURRENT_TIMESTAMP)",
                (uuid.uuid4().hex, m["memory_id"]),
            )
        reinforced += 1
    print(f"  强化: {reinforced} 条记忆 (dry={dry})")

    # 合并重复记忆
    merged = 0
    dupes = conn.execute(
        "SELECT id, content FROM memories WHERE active_state='active'"
    ).fetchall()
    seen_buckets: dict[str, list[str]] = {}
    for m in dupes:
        key = (m["content"] or "").strip().lower()
        if key not in seen_buckets:
            seen_buckets[key] = [m["id"]]
        else:
            seen_buckets[key].append(m["id"])
    for content_key, ids in seen_buckets.items():
        if len(ids) < 2:
            continue
        primary = ids[0]
        for dupe_id in ids[1:]:
            if not dry:
                conn.execute("UPDATE memories SET active_state='superseded', superseded_by=? WHERE id=?",
                             (primary, dupe_id))
            merged += 1
    print(f"  合并: {merged} 个重复 (dry={dry})")

    conn.commit()
    conn.close()

    # ── 总结 ──
    print(f"\n{'='*60}")
    print(f"维护完成 ({mode})")
    print(f"  sessions 回填: {backfilled}")
    print(f"  会话摘要: {summarized}")
    print(f"  叙事反思: {new_refs}")
    print(f"  记忆衰减: {decayed}")
    print(f"  记忆强化: {reinforced}")
    print(f"  重复合并: {merged}")
    print(f"{'='*60}\n")

    if backfilled + summarized + new_refs + decayed + reinforced + merged == 0 and not dry:
        print("一切正常，无需更新 ✅")
    elif dry:
        print("DRY-RUN 完成。去掉 --dry-run 执行 ✅")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())