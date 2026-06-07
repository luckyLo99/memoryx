"""Fusion algorithms for multi-channel retrieval — RRF (Reciprocal Rank Fusion).

Ported from legacy core/fusion.py. This module is independent of any
specific data model and can be used by any retrieval pipeline.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RankedCandidate:
    """A single candidate from one ranked retrieval channel."""

    claim_id: str
    rank: int
    score: float | None = None
    source: str = "unknown"


def reciprocal_rank_fusion(
    ranked_lists: list[list[RankedCandidate]],
    k: int = 60,
) -> dict[str, float]:
    """Fuse multiple ranked lists via Reciprocal Rank Fusion.

    Each list contributes 1/(k + rank) to each candidate's score.
    Final scores are normalised to [0, 1] by dividing by the maximum.

    Args:
        ranked_lists: One list of RankedCandidate per retrieval channel.
        k: RRF constant (default 60, standard value from the literature).

    Returns:
        Dict mapping claim_id → fused score in [0, 1].
    """
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
    """Build a ranked candidate list from an ordered sequence of IDs."""
    return [
        RankedCandidate(claim_id=cid, rank=idx + 1, source=source)
        for idx, cid in enumerate(claim_ids)
    ]
