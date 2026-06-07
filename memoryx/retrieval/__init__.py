from __future__ import annotations

from .engine import HybridRetrievalEngine
from .models import RetrievalIntent, RetrievalResult
from .scorer import (
    ConfidenceLabel,
    ScoreBreakdown,
    access_boost,
    compute_final_score,
    decay_multiplier,
    label_from_score,
    normalize_bm25,
    recency,
    status_penalty,
)
from .fusion import RankedCandidate, make_ranked_candidates, reciprocal_rank_fusion

# --- Legacy re-exports (from memoryx.core, backward compat) ---
from memoryx.core.hybrid_retriever import HybridRetriever as HybridRetriever
from memoryx.core.types import SearchOptions as SearchOptions

__all__ = [
    "HybridRetrievalEngine",
    "RetrievalIntent",
    "RetrievalResult",
    # scorer
    "ConfidenceLabel",
    "ScoreBreakdown",
    "access_boost",
    "compute_final_score",
    "decay_multiplier",
    "label_from_score",
    "normalize_bm25",
    "recency",
    "status_penalty",
    # fusion
    "RankedCandidate",
    "make_ranked_candidates",
    "reciprocal_rank_fusion",
    # legacy core
    "HybridRetriever",
    "SearchOptions",
]
