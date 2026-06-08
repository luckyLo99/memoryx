from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass(slots=True)
class SessionIndexRecord:
    session_id: str
    title: str
    summary: str
    keywords: list[str]
    entities: list[str]
    topics: list[str]
    turn_count: int
    char_count: int
    content_hash: str


class SessionSearchIndexBuilder:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def rebuild_recent(self, *, hours: int = 48, limit: int = 200) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id,
                       COUNT(*) AS turn_count,
                       SUM(length(content)) AS char_count,
                       MIN(created_at) AS started_at,
                       MAX(created_at) AS ended_at,
                       group_concat(role || ': ' || substr(content, 1, 2000), char(10)) AS joined
                FROM conversation_logs
                WHERE session_id IS NOT NULL AND session_id != ''
                  AND REPLACE(created_at, 'T', ' ') >= datetime('now', ?)
                GROUP BY session_id
                ORDER BY ended_at DESC
                LIMIT ?;
                """,
                (f"-{int(hours)} hours", int(limit)),
            ).fetchall()

            count = 0
            for row in rows:
                record = self._build_record(row)
                self._upsert(conn, record, row)
                count += 1

            return count

    def _build_record(self, row: sqlite3.Row) -> SessionIndexRecord:
        text = str(row["joined"] or "")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        tokens = _WORD_RE.findall(text.lower())

        freq: dict[str, int] = {}
        for t in tokens:
            if len(t) < 2:
                continue
            freq[t] = freq.get(t, 0) + 1

        keywords = [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:30]]

        summary = self._extractive_summary(text)
        topics = self._topics_from_keywords(keywords)

        return SessionIndexRecord(
            session_id=str(row["session_id"]),
            title=topics[0] if topics else str(row["session_id"]),
            summary=summary,
            keywords=keywords,
            entities=[],
            topics=topics[:8],
            turn_count=int(row["turn_count"] or 0),
            char_count=int(row["char_count"] or 0),
            content_hash=content_hash,
        )

    def _extractive_summary(self, text: str, *, max_chars: int = 1200) -> str:
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        important = []
        markers = [
            "完成", "修复", "问题", "结论", "下一步",
            "lesson", "error", "失败", "通过", "小红书", "学习",
        ]
        for line in lines:
            if any(m.lower() in line.lower() for m in markers):
                important.append(line)
            if sum(len(x) for x in important) >= max_chars:
                break

        if not important:
            important = lines[:8]

        return "\n".join(important)[:max_chars]

    def _topics_from_keywords(self, keywords: list[str]) -> list[str]:
        preferred = [
            "memoryx", "hermes", "feishu", "p14", "p15", "p16", "p17",
            "小红书", "学习", "搜索", "embedding",
        ]
        topics = [k for k in preferred if k.lower() in keywords]
        for k in keywords:
            if k not in topics:
                topics.append(k)
            if len(topics) >= 8:
                break
        return topics

    def _upsert(self, conn: sqlite3.Connection, record: SessionIndexRecord, source_row: sqlite3.Row) -> None:
        conn.execute(
            """
            INSERT INTO session_search_index(
                session_id, title, started_at, ended_at, turn_count, char_count,
                summary, keywords_json, entities_json, topics_json,
                content_hash, summary_model, summary_updated_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'extractive-v1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                title=excluded.title,
                started_at=excluded.started_at,
                ended_at=excluded.ended_at,
                turn_count=excluded.turn_count,
                char_count=excluded.char_count,
                summary=excluded.summary,
                keywords_json=excluded.keywords_json,
                entities_json=excluded.entities_json,
                topics_json=excluded.topics_json,
                content_hash=excluded.content_hash,
                summary_model=excluded.summary_model,
                summary_updated_at=excluded.summary_updated_at,
                updated_at=CURRENT_TIMESTAMP;
            """,
            (
                record.session_id,
                record.title,
                source_row["started_at"],
                source_row["ended_at"],
                record.turn_count,
                record.char_count,
                record.summary,
                json.dumps(record.keywords, ensure_ascii=False),
                json.dumps(record.entities, ensure_ascii=False),
                json.dumps(record.topics, ensure_ascii=False),
                record.content_hash,
            ),
        )

        conn.execute(
            "DELETE FROM session_search_fts WHERE session_id=?;",
            (record.session_id,),
        )
        conn.execute(
            """
            INSERT INTO session_search_fts(session_id, title, summary, keywords, entities, topics)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                record.session_id,
                record.title,
                record.summary,
                " ".join(record.keywords[:50]),
                " ".join(record.entities[:50]),
                " ".join(record.topics[:20]),
            ),
        )