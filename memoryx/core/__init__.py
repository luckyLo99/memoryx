"""DEPRECATED — Legacy core module.

This module provides backward-compatible re-exports for code that still
imports from ``memoryx.core``.  All functionality has been migrated to the
canonical locations listed below.

Migration targets
-----------------
- ``memoryx.retrieval.scorer``  → scoring formulas (ScoreBreakdown, compute_final_score, …)
- ``memoryx.retrieval.fusion``  → RRF fusion (reciprocal_rank_fusion, …)
- ``memoryx.embeddings.vector_store`` → VectorProvider, VectorHit, NullVectorProvider
- ``memoryx.cognitive.conflict`` → conflict helpers (new_conflict_group_id, same_slot, …)

Legacy items kept here for runtime compatibility:
- MemoryKernel, Retriever, HybridRetriever, HermesAdapter (claims/evidence schema)
- Claim, ClaimVersion, Evidence, RetrievalResult (legacy types)
"""

from __future__ import annotations

import warnings as _warnings

# ---------------------------------------------------------------------------
# Re-exports from new canonical locations
# ---------------------------------------------------------------------------

# Vector abstraction → memoryx.embeddings.vector_store
from memoryx.embeddings.vector_store import (
    NullVectorProvider as NullVectorProvider,
    VectorHit as VectorHit,
    VectorProvider as VectorProvider,
)

# Scoring → memoryx.retrieval.scorer
from memoryx.retrieval.scorer import (
    ScoreBreakdown as ScoreBreakdown,
    compute_final_score as compute_final_score,
    label_from_score as label_from_score,
    normalize_bm25 as normalize_bm25,
    recency as recency,
    decay_multiplier as decay_multiplier,
    access_boost as access_boost,
    status_penalty as status_penalty,
)

# Fusion → memoryx.retrieval.fusion
from memoryx.retrieval.fusion import (
    RankedCandidate as RankedCandidate,
    make_ranked_candidates as make_ranked_candidates,
    reciprocal_rank_fusion as reciprocal_rank_fusion,
)

# Conflict helpers → memoryx.cognitive.conflict
from memoryx.cognitive.conflict import (
    new_conflict_group_id as new_conflict_group_id,
    same_slot as same_slot,
    should_reinforce as should_reinforce,
    should_supersede as should_supersede,
)

# ---------------------------------------------------------------------------
# Legacy imports (old data model — claims/evidence schema)
# ---------------------------------------------------------------------------

from .schema import apply_schema as apply_schema
from .kernel import MemoryKernel as MemoryKernel
from .retriever import Retriever as Retriever
from .hybrid_retriever import HybridRetriever as HybridRetriever
from .types import Claim as Claim, ClaimVersion as ClaimVersion
from .types import Evidence as Evidence, SearchOptions as SearchOptions
from .types import RetrievalResult as LegacyRetrievalResult
from .hermes_adapter import HermesAdapter as HermesAdapter

# Legacy alias kept for source compatibility
RetrievalResult = LegacyRetrievalResult

# ---------------------------------------------------------------------------
# Deprecation guard
# ---------------------------------------------------------------------------

_warnings.warn(
    "memoryx.core is deprecated. "
    "See https://github.com/luckyl214/memoryx/wiki/memoryx-core-deprecation for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    # Ported to new locations
    "NullVectorProvider", "VectorHit", "VectorProvider",
    "ScoreBreakdown", "compute_final_score", "label_from_score",
    "normalize_bm25", "recency", "decay_multiplier", "access_boost",
    "status_penalty",
    "RankedCandidate", "make_ranked_candidates", "reciprocal_rank_fusion",
    "new_conflict_group_id", "same_slot", "should_reinforce", "should_supersede",
    # Legacy
    "apply_schema", "MemoryKernel", "Retriever", "HybridRetriever",
    "Claim", "ClaimVersion", "Evidence", "RetrievalResult", "SearchOptions",
    "HermesAdapter",
]
