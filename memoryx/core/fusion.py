from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class RankedCandidate:
    claim_id: str
    rank: int
    score: float | None = None
    source: str = "unknown"

def reciprocal_rank_fusion(
    ranked_lists: list[list[RankedCandidate]],
    k: int = 60,
) -> dict[str, float]:
    fused: dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        for item in ranked:
            if item.rank <= 0:
                continue
            fused[item.claim_id] += 1.0 / (k + item.rank)
    if not fused:
        return {}
    max_score = max(fused.values())
    if max_score <= 0:
        return dict(fused)
    return {claim_id: score / max_score for claim_id, score in fused.items()}

def make_ranked_candidates(
    claim_ids: Iterable[str],
    source: str,
) -> list[RankedCandidate]:
    return [
        RankedCandidate(claim_id=claim_id, rank=index + 1, source=source)
        for index, claim_id in enumerate(claim_ids)
    ]
