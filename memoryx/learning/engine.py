from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MASTERY_LEVELS = ["知道", "会用", "会改", "会设计", "会迁移"]


@dataclass(slots=True)
class LearningSessionResult:
    learning_session_id: str
    project_id: str
    session_id: str
    status: str


class LearningEngine:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def ensure_project(
        self,
        *,
        project_id: str,
        name: str,
        objective: str,
        owner: str = "Drew",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_projects(id, name, objective, owner, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    objective=excluded.objective,
                    owner=excluded.owner,
                    metadata_json=excluded.metadata_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    project_id,
                    name,
                    objective,
                    owner,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )

    def start_session(
        self,
        *,
        project_id: str,
        session_id: str,
        title: str,
        topic: str,
        goal: str,
        mastery_target: str = "会用",
        metadata: dict[str, Any] | None = None,
    ) -> LearningSessionResult:
        if mastery_target not in MASTERY_LEVELS:
            mastery_target = "会用"

        learning_session_id = uuid.uuid4().hex

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_sessions(
                    id, project_id, session_id, title, topic, goal,
                    mastery_target, status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?);
                """,
                (
                    learning_session_id,
                    project_id,
                    session_id,
                    title,
                    topic,
                    goal,
                    mastery_target,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )

        return LearningSessionResult(
            learning_session_id=learning_session_id,
            project_id=project_id,
            session_id=session_id,
            status="running",
        )

    def end_session(
        self,
        *,
        session_id: str,
        summary: str,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = time.time()

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM learning_sessions
                WHERE session_id=? AND status='running'
                ORDER BY started_at DESC
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()

            if not row:
                return {"status": "no_running_session", "session_id": session_id}

            started_raw = row["started_at"]
            try:
                started_epoch = conn.execute(
                    "SELECT strftime('%s', ?) AS ts;",
                    (started_raw,),
                ).fetchone()["ts"]
                duration = int(now - int(started_epoch))
            except Exception:
                duration = None

            conn.execute(
                """
                UPDATE learning_sessions
                SET status='done',
                    ended_at=CURRENT_TIMESTAMP,
                    duration_seconds=?,
                    summary=?
                WHERE id=?;
                """,
                (duration, summary, row["id"]),
            )

            for artifact in artifacts or []:
                self._add_artifact(
                    conn=conn,
                    project_id=row["project_id"],
                    session_id=session_id,
                    artifact_type=artifact.get("artifact_type", "summary"),
                    title=artifact.get("title", ""),
                    content=artifact.get("content", ""),
                    path=artifact.get("path"),
                    trust_score=float(artifact.get("trust_score", 0.7)),
                    source_type=artifact.get("source_type", "learning_session"),
                )

            return {
                "status": "done",
                "learning_session_id": row["id"],
                "session_id": session_id,
                "duration_seconds": duration,
            }

    def _add_artifact(
        self,
        *,
        conn: sqlite3.Connection,
        project_id: str,
        session_id: str,
        artifact_type: str,
        title: str,
        content: str,
        path: str | None = None,
        trust_score: float = 0.7,
        source_type: str = "learning_session",
    ) -> str:
        artifact_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO learning_artifacts(
                id, project_id, session_id, artifact_type, title, content,
                path, trust_score, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                artifact_id,
                project_id,
                session_id,
                artifact_type,
                title,
                content,
                path,
                trust_score,
                source_type,
            ),
        )
        return artifact_id

    def record_mastery_check(
        self,
        *,
        project_id: str,
        session_id: str,
        topic: str,
        level: str,
        evidence: list[str],
        weak_points: list[str],
        next_tasks: list[str],
        score: float,
    ) -> str:
        if level not in MASTERY_LEVELS:
            level = "知道"

        check_id = uuid.uuid4().hex

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mastery_checks(
                    id, project_id, session_id, topic, level,
                    evidence_json, weak_points_json, next_tasks_json, score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    check_id,
                    project_id,
                    session_id,
                    topic,
                    level,
                    json.dumps(evidence, ensure_ascii=False),
                    json.dumps(weak_points, ensure_ascii=False),
                    json.dumps(next_tasks, ensure_ascii=False),
                    float(score),
                ),
            )

        return check_id

    def get_project_progress(self, *, project_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            sessions = conn.execute(
                """
                SELECT topic,
                       COUNT(*) AS n,
                       SUM(COALESCE(duration_seconds, 0)) AS seconds
                FROM learning_sessions
                WHERE project_id=?
                GROUP BY topic
                ORDER BY seconds DESC;
                """,
                (project_id,),
            ).fetchall()

            mastery = conn.execute(
                """
                SELECT topic, level, score, created_at
                FROM mastery_checks
                WHERE project_id=?
                ORDER BY created_at DESC;
                """,
                (project_id,),
            ).fetchall()

        return {
            "project_id": project_id,
            "time_by_topic": [dict(r) for r in sessions],
            "mastery_history": [dict(r) for r in mastery],
        }