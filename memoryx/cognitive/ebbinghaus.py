"""Ebbinghaus forgetting curve with spaced repetition scheduling.

Scientific foundations:
- Ebbinghaus forgetting curve: R = exp(-t/S) where S is memory strength
- Spacing effect: expanding intervals improve retention
- Retrieval practice effect (testing effect): each recall strengthens
- Leitner system: optimal review intervals based on performance

References:
- Ebbinghaus, H. (1885). Memory: A Contribution to Experimental Psychology
- Cepeda et al. (2006). Distributed practice in verbal recall tasks
- Kornell & Bjork (2008). Optimising self-regulated learning
- Murre & Dros (2015). Replication of Ebbinghaus forgetting curve
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RetrievalOutcome(Enum):
    PERFECT = "perfect"
    GOOD = "good"
    HARD = "hard"
    FAIL = "fail"


INTERVAL_TABLE = {
    RetrievalOutcome.PERFECT: [0, 3600, 21600, 86400, 259200, 604800, 1209600, 2592000, 7776000],
    RetrievalOutcome.GOOD:    [0, 1800, 10800, 43200, 172800, 432000, 864000, 1814400, 5184000],
    RetrievalOutcome.HARD:    [0, 600, 3600, 14400, 43200, 129600, 259200, 604800, 1209600],
    RetrievalOutcome.FAIL:    [0, 60, 600, 3600, 10800, 43200, 86400, 172800, 432000],
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryStrength:
    encoding_strength: float = 0.5
    retrieval_count: int = 0
    strength_s: float = 1.0
    elapsed_since_review: float = 0.0
    next_review_interval: float = 3600.0
    last_outcome: RetrievalOutcome = RetrievalOutcome.GOOD
    half_life: float = 86400.0
    last_accessed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            'encoding_strength': self.encoding_strength,
            'retrieval_count': self.retrieval_count,
            'strength_s': self.strength_s,
            'elapsed_since_review': self.elapsed_since_review,
            'next_review_interval': self.next_review_interval,
            'last_outcome': self.last_outcome.value,
            'half_life': self.half_life,
            'last_accessed_at': self.last_accessed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryStrength:
        return cls(
            encoding_strength=float(data.get('encoding_strength', 0.5)),
            retrieval_count=int(data.get('retrieval_count', 0)),
            strength_s=float(data.get('strength_s', 1.0)),
            elapsed_since_review=float(data.get('elapsed_since_review', 0.0)),
            next_review_interval=float(data.get('next_review_interval', 3600.0)),
            last_outcome=RetrievalOutcome(data.get('last_outcome', 'good')),
            half_life=float(data.get('half_life', 86400.0)),
            last_accessed_at=float(data.get('last_accessed_at', 0.0)),
        )

class EbbinghausForgettingCurve:
    @staticmethod
    def retention(strength: MemoryStrength, now: float | None = None) -> float:
        if now is None:
            now = time.time()
        elapsed = max(0.0, now - strength.last_accessed_at)
        strength.elapsed_since_review = elapsed
        if strength.strength_s <= 0:
            return 0.0
        retention_val = math.exp(-elapsed / strength.strength_s)
        importance_floor = 0.05 * strength.encoding_strength
        return max(importance_floor, min(1.0, retention_val))

    @staticmethod
    def update_after_retrieval(
        strength: MemoryStrength, outcome: RetrievalOutcome,
        now: float | None = None,
    ) -> MemoryStrength:
        if now is None:
            now = time.time()
        elapsed = max(0.0, now - strength.last_accessed_at)
        strength.elapsed_since_review = elapsed
        if outcome == RetrievalOutcome.FAIL:
            strength.retrieval_count = max(0, strength.retrieval_count - 1)
            strength.strength_s = strength.strength_s * 0.7
            strength.next_review_interval = INTERVAL_TABLE[RetrievalOutcome.FAIL][0]
            strength.last_outcome = RetrievalOutcome.FAIL
        else:
            strength.retrieval_count += 1
            practice_boost = math.log2(max(2, strength.retrieval_count + 1))
            strength.strength_s = strength.strength_s * (1.0 + 0.15 * practice_boost)
            strength.strength_s = min(strength.strength_s, 315360000.0)
            stage = min(strength.retrieval_count, len(INTERVAL_TABLE[outcome]) - 1)
            stage = max(0, stage)
            strength.next_review_interval = INTERVAL_TABLE[outcome][stage]
            strength.last_outcome = outcome
        strength.last_accessed_at = now
        return strength

    @staticmethod
    def initial_strength(importance: float = 0.5) -> MemoryStrength:
        base = 3600.0 + (604800.0 - 3600.0) * max(0.0, min(1.0, importance))
        half = base * math.log(2)
        return MemoryStrength(
            encoding_strength=importance,
            strength_s=base,
            half_life=half,
            last_accessed_at=time.time(),
        )

    @staticmethod
    def decay_multiplier(strength: MemoryStrength, mn: float = 0.20, mx: float = 1.15) -> float:
        r = EbbinghausForgettingCurve.retention(strength)
        return mn + (mx - mn) * r

    @staticmethod
    def is_due_for_review(strength: MemoryStrength, now: float | None = None) -> bool:
        if now is None:
            now = time.time()
        return (now - strength.last_accessed_at) >= strength.next_review_interval

class SpacedRepetitionScheduler:
    LEITNER_INTERVALS = [86400, 259200, 604800, 1209600, 2592000, 7776000]

    @staticmethod
    def schedule_next_review(strength: MemoryStrength, outcome: RetrievalOutcome) -> float:
        stage = min(strength.retrieval_count, len(INTERVAL_TABLE[outcome]) - 1)
        stage = max(0, stage)
        return INTERVAL_TABLE[outcome][stage]

    @staticmethod
    def box_for_memory(strength: MemoryStrength) -> int:
        iv = strength.next_review_interval
        for i, bi in enumerate(SpacedRepetitionScheduler.LEITNER_INTERVALS):
            if iv <= bi:
                return i
        return 5

    @staticmethod
    def batch_due_memories(
        strengths: list[tuple[str, MemoryStrength]],
        max_items: int = 100,
        now: float | None = None,
    ) -> list[tuple[str, MemoryStrength]]:
        if now is None:
            now = time.time()
        due = [(mid, s) for mid, s in strengths
               if (now - s.last_accessed_at) >= s.next_review_interval]
        due.sort(key=lambda x: (now - x[1].last_accessed_at) - x[1].next_review_interval,
                 reverse=True)
        return due[:max_items]
