#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys


DB = os.getenv("MEMORYX_DB_PATH", "/home/lucky/memoryx/data/memoryx.db")


def ok(msg: str) -> None:
    print("OK:", msg)


def fail(msg: str) -> None:
    print("FAIL:", msg)
    raise SystemExit(1)


def scalar(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    if not row:
        return 0
    return list(row)[0] or 0


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    required = {
        "learning_projects",
        "learning_sessions",
        "learning_artifacts",
        "mastery_checks",
        "skill_atoms",
        "skill_candidates",
        "skill_drafts",
        "skill_ux_scores",
    }

    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view');"
        )
    }

    missing = sorted(required - tables)
    if missing:
        fail(f"missing tables: {missing}")
    ok("P16 tables exist")

    # Smoke insert learning project/session.
    conn.execute(
        """
        INSERT OR REPLACE INTO learning_projects(id, name, objective, owner)
        VALUES ('p16-gate-project', 'P16 Gate Project', 'verify learning loop', 'Drew');
        """
    )

    conn.execute(
        """
        INSERT INTO learning_sessions(
            id, project_id, session_id, title, topic, goal, mastery_target, status
        ) VALUES (
            'p16-gate-session-id',
            'p16-gate-project',
            'p16-gate-session',
            'P16 Gate Session',
            'MemoryX',
            'verify learning session lifecycle',
            '会用',
            'running'
        )
        ON CONFLICT(id) DO NOTHING;
        """
    )

    conn.execute(
        """
        INSERT INTO mastery_checks(
            id, project_id, session_id, topic, level,
            evidence_json, weak_points_json, next_tasks_json, score
        ) VALUES (
            'p16-gate-mastery',
            'p16-gate-project',
            'p16-gate-session',
            'MemoryX',
            '会用',
            '["can explain the workflow"]',
            '["needs real use"]',
            '["run one real learning session"]',
            0.7
        )
        ON CONFLICT(id) DO NOTHING;
        """
    )

    conn.execute(
        """
        INSERT INTO skill_atoms(
            id, atom_type, intent, summary, raw_excerpt,
            tags_json, evidence_json, trust_score
        ) VALUES (
            'p16-gate-atom',
            'learning_pattern',
            'verify skill atom',
            'A high-trust learning atom is captured.',
            'User explicitly asked for a reusable learning pattern.',
            '["learning","memoryx"]',
            '[{"source":"gate"}]',
            0.9
        )
        ON CONFLICT(id) DO NOTHING;
        """
    )

    conn.commit()

    n_projects = scalar(conn, "SELECT COUNT(*) FROM learning_projects;")
    n_sessions = scalar(conn, "SELECT COUNT(*) FROM learning_sessions;")
    n_atoms = scalar(conn, "SELECT COUNT(*) FROM skill_atoms;")

    if n_projects < 1 or n_sessions < 1 or n_atoms < 1:
        fail("smoke data not persisted")

    ok("learning project/session/mastery/atom smoke passed")

    print("P16 LEARNING SKILL GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())