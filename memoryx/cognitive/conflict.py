from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


NEGATIONS = ["不", "不是", "没有", "never", "not", "no", "dislike", "hate"]
PREFERENCE_WORDS = ["喜欢", "不喜欢", "偏好", "讨厌", "prefer", "like", "dislike"]


@dataclass(slots=True)
class ConflictCandidate:
    memory_a_id: str
    memory_b_id: str
    conflict_type: str
    confidence: float
    summary: str


class MemoryConflictDetector:
    """Lightweight semantic conflict detection for new memories.

    Detects preference/fact shifts: two related statements with opposite
    sentiment (negated vs non-negated) within the same semantic cluster.

    Priority: fewer false positives > perfect recall.
    """

    def __init__(self, *, repository, retrieval_engine=None) -> None:
        self.repository = repository
        self.retrieval_engine = retrieval_engine

    async def detect_for_new_memory(
        self, memory: dict[str, Any], *, limit: int = 8
    ) -> list[ConflictCandidate]:
        content = str(memory.get("content") or "")
        if not content.strip():
            return []

        candidates = await self._similar_memories(content, limit=limit)
        conflicts: list[ConflictCandidate] = []

        for old in candidates:
            old_id = str(old.get("id") or old.get("memory_id") or "")
            new_id = str(memory.get("id") or memory.get("memory_id") or "")
            if not old_id or old_id == new_id:
                continue

            old_content = str(old.get("content") or "")
            if self._looks_conflicting(old_content, content):
                conflicts.append(
                    ConflictCandidate(
                        memory_a_id=old_id,
                        memory_b_id=new_id,
                        conflict_type="preference_or_fact_shift",
                        confidence=0.72,
                        summary=f"Possible conflict: OLD={old_content[:120]} NEW={content[:120]}",
                    )
                )

        return conflicts

    async def persist_conflicts(self, conflicts: list[ConflictCandidate]) -> None:
        for c in conflicts:
            await self.repository.db.execute(
                """
                INSERT INTO memory_conflicts(
                    id, memory_a_id, memory_b_id, conflict_type, confidence, summary
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    uuid4().hex,
                    c.memory_a_id,
                    c.memory_b_id,
                    c.conflict_type,
                    c.confidence,
                    c.summary,
                ),
            )

    async def _similar_memories(
        self, content: str, *, limit: int
    ) -> list[dict[str, Any]]:
        if self.retrieval_engine is not None:
            results = await self.retrieval_engine.retrieve(
                query=content,
                query_vector=[],
                limit=limit,
                include_global=True,
                include_lessons=False,
            )
            return [
                r
                if isinstance(r, dict)
                else getattr(r, "__dict__", {"content": str(r)})
                for r in results
            ]

        rows = await self.repository.search_full_text(content[:80], limit=limit)
        return [dict(r) for r in rows]

    def _looks_conflicting(self, a: str, b: str) -> bool:
        a_l = a.lower()
        b_l = b.lower()

        if any(w in a_l for w in PREFERENCE_WORDS) and any(
            w in b_l for w in PREFERENCE_WORDS
        ):
            a_neg = any(n in a_l for n in NEGATIONS)
            b_neg = any(n in b_l for n in NEGATIONS)
            if a_neg != b_neg:
                return self._token_overlap(a_l, b_l) >= 0.25

        return False

    def _token_overlap(self, a: str, b: str) -> float:
        ta = set(re.findall(r"[\w\u4e00-\u9fff]+", a))
        tb = set(re.findall(r"[\w\u4e00-\u9fff]+", b))
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / max(len(ta | tb), 1)