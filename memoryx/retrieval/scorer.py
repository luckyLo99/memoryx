"""Scoring utilities for retrieval - ported from legacy core/scoring.py.

Provides composable score components (recency, decay, boost, penalty)
and a unified ScoreBreakdown that can be used by any retrieval path.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from memoryx.cognitive.ebbinghaus import EbbinghausForgettingCurve, MemoryStrength, RetrievalOutcome

from datetime import datetime, timezone
from typing import Any, Literal

ConfidenceLabel = Literal["high", "medium", "low", "rejected"]


@dataclass(frozen=True)
class ScoreBreakdown:
    """Detailed score breakdown for a single retrieval result."""

    bm25_score: float | None = None
    lexical_score: float = 0.0
    vector_score: float | None = None
    recency_score: float = 0.0
    importance_score: float = 0.0
    confidence_score: float = 0.0
    decay_multiplier: float = 1.0
    access_boost: float = 0.0
    status_penalty: float = 0.0
    rrf_score: float | None = None
    final_score: float = 0.0


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def normalize_bm25(bm25_score: float | None) -> float:
    if bm25_score is None:
        return 0.0
    return _clamp(1.0 / (1.0 + abs(float(bm25_score))))


def recency(updated_at: str | None, half_life_days: float = 30.0) -> float:
    dt = _parse_dt(updated_at)
    if dt is None:
        return 0.35
    age_days = max((_utcnow() - dt).total_seconds() / 86400.0, 0.0)
    return _clamp(math.exp(-math.log(2) * age_days / half_life_days))


def access_boost(access_count: int, last_accessed_at: str | None) -> float:
    count_component = _clamp(math.log1p(max(access_count, 0)) / 8.0)
    dt = _parse_dt(last_accessed_at)
    if dt is None:
        return count_component
    age_days = max((_utcnow() - dt).total_seconds() / 86400.0, 0.0)
    recent_component = 0.25 * math.exp(-math.log(2) * age_days / 14.0)
    return _clamp(count_component + recent_component)


def decay_multiplier(
    last_accessed_at: str | None,
    updated_at: str | None,
    min_multiplier: float = 0.30,
    max_multiplier: float = 1.15,
    half_life_days: float = 60.0,
) -> float:
    anchor = _parse_dt(last_accessed_at) or _parse_dt(updated_at)
    if anchor is None:
        return 1.0
    age_days = max((_utcnow() - anchor).total_seconds() / 86400.0, 0.0)
    raw = math.exp(-math.log(2) * age_days / half_life_days)
    return _clamp(
        min_multiplier + (max_multiplier - min_multiplier) * raw,
        min_multiplier,
        max_multiplier,
    )


def ebbinghaus_decay_multiplier(
    importance: float = 0.5,
    retrieval_count: int = 0,
    last_accessed_at: str | None = None,
    updated_at: str | None = None,
    min_mult: float = 0.20,
    max_mult: float = 1.15,
) -> float:
    # Ebbinghaus-forgetting-curve decay multiplier
    if last_accessed_at is None and updated_at is None:
        return 1.0
    strength = EbbinghausForgettingCurve.initial_strength(importance)
    strength.retrieval_count = max(0, retrieval_count)
    if retrieval_count > 0:
        for _ in range(retrieval_count):
            strength = EbbinghausForgettingCurve.update_after_retrieval(
                strength, RetrievalOutcome.GOOD,
                strength.last_accessed_at + 1.0,
            )
    return EbbinghausForgettingCurve.decay_multiplier(strength, min_mult, max_mult)

def status_penalty(status: str) -> float:
    return {
        "active": 0.0,
        "candidate": 0.10,
        "conflicted": 0.25,
        "expired": 0.35,
        "superseded": 0.60,
        "quarantined": 0.80,
        "revoked": 1.00,
    }.get(status, 0.50)


def label_from_score(final_score: float) -> ConfidenceLabel:
    if final_score >= 0.70:
        return "high"
    if final_score >= 0.40:
        return "medium"
    if final_score >= 0.15:
        return "low"
    return "rejected"


def compute_final_score(
    *,
    bm25_score: float | None,
    vector_score: float | None,
    updated_at: str | None,
    last_accessed_at: str | None,
    access_count: int,
    importance: float,
    confidence: float,
    status: str,
    rrf_score: float | None = None,
) -> ScoreBreakdown:
    lexical = normalize_bm25(bm25_score)
    recency_ = recency(updated_at)
    access = access_boost(access_count, last_accessed_at)
    decay = decay_multiplier(last_accessed_at, updated_at)
    penalty = status_penalty(status)

    if rrf_score is not None:
        base = (
            0.40 * _clamp(rrf_score)
            + 0.15 * lexical
            + 0.10 * recency_
            + 0.15 * _clamp(importance)
            + 0.15 * _clamp(confidence)
            + 0.05 * access
        )
    elif vector_score is not None:
        base = (
            0.30 * lexical
            + 0.30 * _clamp(vector_score)
            + 0.10 * recency_
            + 0.12 * _clamp(importance)
            + 0.13 * _clamp(confidence)
            + 0.05 * access
        )
    else:
        base = (
            0.45 * lexical
            + 0.15 * recency_
            + 0.15 * _clamp(importance)
            + 0.15 * _clamp(confidence)
            + 0.10 * access
        )

    final = _clamp(base * decay - penalty)

    return ScoreBreakdown(
        bm25_score=bm25_score,
        lexical_score=lexical,
        vector_score=vector_score,
        recency_score=recency_,
        importance_score=_clamp(importance),
        confidence_score=_clamp(confidence),
        decay_multiplier=decay,
        access_boost=access,
        status_penalty=penalty,
        rrf_score=rrf_score,
        final_score=final,
    )


def breakdown_to_dict(score: ScoreBreakdown) -> dict[str, Any]:
    return asdict(score)


# Backward-compatibility aliases for legacy core/ importers
confidence_label = label_from_score
score_to_explanation = breakdown_to_dict
