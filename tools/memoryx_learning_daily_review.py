#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[misc]

REPO_DIR = Path(__file__).resolve().parent.parent
DB = os.getenv("MEMORYX_DB_PATH", str(REPO_DIR / 'data' / 'memoryx.db'))
OUT_DIR = REPO_DIR / "study"


def _get_cst_tz():
    """Return Asia/Shanghai timezone, or None if unavailable (graceful fallback)."""
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo("Asia/Shanghai")
    except ZoneInfoNotFoundError:
        return None


CST = _get_cst_tz()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    sessions = conn.execute(
        """
        SELECT project_id, session_id, topic, goal, summary, duration_seconds,
               started_at, ended_at
        FROM learning_sessions
        WHERE date(started_at) = date('now', 'localtime')
        ORDER BY started_at ASC;
        """
    ).fetchall()

    artifacts = conn.execute(
        """
        SELECT project_id, artifact_type, title,
               substr(content, 1, 500) AS preview, trust_score
        FROM learning_artifacts
        WHERE date(created_at) = date('now', 'localtime')
        ORDER BY created_at ASC;
        """
    ).fetchall()

    checks = conn.execute(
        """
        SELECT project_id, topic, level, score, weak_points_json, next_tasks_json
        FROM mastery_checks
        WHERE date(created_at) = date('now', 'localtime')
        ORDER BY created_at ASC;
        """
    ).fetchall()

    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
    path = OUT_DIR / f"daily-learning-review-{datetime.now(CST).strftime('%Y%m%d')}.md"

    lines = [
        f"# MemoryX Daily Learning Review · {now}",
        "",
        "## Sessions",
    ]

    if sessions:
        for s in sessions:
            minutes = int(s["duration_seconds"] or 0) // 60
            lines.append(
                f"- {s['project_id']} / {s['topic']} · {minutes} min · "
                f"{s['summary'] or s['goal']}"
            )
    else:
        lines.append("- No learning sessions recorded today.")

    lines.extend(["", "## Artifacts"])
    if artifacts:
        for a in artifacts:
            lines.append(
                f"- [{a['artifact_type']}] {a['title']} · trust={a['trust_score']}"
            )
    else:
        lines.append("- No artifacts recorded today.")

    lines.extend(["", "## Mastery Checks"])
    if checks:
        for c in checks:
            lines.append(f"- {c['topic']} · {c['level']} · score={c['score']}")
    else:
        lines.append("- No mastery checks recorded today.")

    lines.extend(["", "## Next Actions (auto-generated)", ""])
    if not sessions and not artifacts and not checks:
        lines.append("No learning activity today. Restart tomorrow.")
    else:
        lines.append("Review today's artifacts and decide on tomorrow's topic.")
        lines.append("If a mastery check was done, focus on weak points next time.")
        lines.append("Run distill_recent if enough high-trust atoms have accumulated.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        {
            "ok": True,
            "path": str(path),
            "sessions": len(sessions),
            "artifacts": len(artifacts),
            "checks": len(checks),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())