from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import math
from typing import Any

from .types import ConfidenceLabel, ScoreBreakdown

def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))

def normalize_bm25(bm25_score: float | None) -> float:
    if bm25_score is None:
        return 0.0
    return clamp(1.0 / (1.0 + abs(float(bm25_score))))

def recency_score(updated_at: str | None, half_life_days: float = 30.0) -> float:
    dt = parse_dt(updated_at)
    if dt is None:
        return 0.35
    age_days = max((utcnow() - dt).total_seconds() / 86400.0, 0.0)
    return clamp(math.exp(-math.log(2) * age_days / half_life_days))

def access_boost(access_count: int, last_accessed_at: str | None) -> float:
    count_component = clamp(math.log1p(max(access_count, 0)) / 8.0)
    dt = parse_dt(last_accessed_at)
    if dt is None:
        return count_component
    age_days = max((utcnow() - dt).total_seconds() / 86400.0, 0.0)
    recent_component = 0.25 * math.exp(-math.log(2) * age_days / 14.0)
    return clamp(count_component + recent_component)

def decay_multiplier(
    last_accessed_at: str | None,
    updated_at: str | None,
    min_multiplier: float = 0.30,
    max_multiplier: float = 1.15,
    half_life_days: float = 60.0,
) -> float:
    anchor = parse_dt(last_accessed_at) or parse_dt(updated_at)
    if anchor is None:
        return 1.0
    age_days = max((utcnow() - anchor).total_seconds() / 86400.0, 0.0)
    raw = math.exp(-math.log(2) * age_days / half_life_days)
    return clamp(min_multiplier + (max_multiplier - min_multiplier) * raw, min_multiplier, max_multiplier)

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

def confidence_label(final_score: float) -> ConfidenceLabel:
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
    recency = recency_score(updated_at)
    access = access_boost(access_count, last_accessed_at)
    decay = decay_multiplier(last_accessed_at, updated_at)
    penalty = status_penalty(status)

    if rrf_score is not None:
        base = (
            0.40 * clamp(rrf_score)
            + 0.15 * lexical + 0.10 * recency
            + 0.15 * clamp(importance) + 0.15 * clamp(confidence)
            + 0.05 * access
        )
    elif vector_score is not None:
        base = (
            0.30 * lexical + 0.30 * clamp(vector_score)
            + 0.10 * recency
            + 0.12 * clamp(importance) + 0.13 * clamp(confidence)
            + 0.05 * access
        )
    else:
        base = (
            0.45 * lexical + 0.15 * recency
            + 0.15 * clamp(importance) + 0.15 * clamp(confidence)
            + 0.10 * access
        )

    final = clamp(base * decay - penalty)

    return ScoreBreakdown(
        bm25_score=bm25_score, lexical_score=lexical,
        vector_score=vector_score, recency_score=recency,
        importance_score=clamp(importance), confidence_score=clamp(confidence),
        decay_multiplier=decay, access_boost=access,
        status_penalty=penalty, rrf_score=rrf_score,
        final_score=final,
    )

def score_to_explanation(score: ScoreBreakdown) -> dict[str, Any]:
    return asdict(score)
