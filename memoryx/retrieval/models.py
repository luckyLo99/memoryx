from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RetrievalIntent(StrEnum):
    CODING = "coding"
    PLANNING = "planning"
    PREFERENCE = "preference"
    EMOTIONAL = "emotional"
    PROJECT = "project"
    TROUBLESHOOTING = "troubleshooting"
    WORKFLOW = "workflow"
    DEBUGGING = "debugging"
    DEPLOYMENT = "deployment"


@dataclass(slots=True)
class RetrievalResult:
    memory_id: str
    content: str
    memory_type: str
    scope: str
    semantic_score: float
    keyword_score: float
    temporal_score: float
    entity_score: float
    importance_score: float
    episodic_score: float
    final_score: float
    explanation: str
    layer_boost: float = 0.0


@dataclass
class RetrievalTrace:
    """Read-only trace for retrieval observability (24.4-D).

    Records counts and plan names only — never raw content, DB path,
    secret, or candidate hidden text.
    """
    query_plan_used: str | None = None
    fallback_steps: list[str] = field(default_factory=list)
    fallback_used: bool = False
    vector_available: bool = False
    raw_hits: int = 0
    visible_hits: int = 0
    dedup_dropped: int = 0
    hidden_candidates: int = 0
    hidden_session: int = 0
    hidden_lessons: int = 0
    hidden_state: int = 0
    layer_boost_applied: int = 0
    fetch_limit: int | None = None
    fallback_fetch_limit: int | None = None
    hydrated_count: int = 0
    get_memory_count: int = 0
    batch_hydration_count: int = 0  # 24.6-B: number of batch_get_memories calls
    cache_hit_count: int = 0   # 24.7-B: hydration_cache hits within request
    cache_miss_count: int = 0  # 24.7-B: hydration_cache misses within request

    def to_dict(self) -> dict:
        return {
            "query_plan_used": self.query_plan_used,
            "fallback_steps": self.fallback_steps,
            "fallback_used": self.fallback_used,
            "vector_available": self.vector_available,
            "raw_hits": self.raw_hits,
            "visible_hits": self.visible_hits,
            "dedup_dropped": self.dedup_dropped,
            "hidden_candidates": self.hidden_candidates,
            "hidden_session": self.hidden_session,
            "hidden_lessons": self.hidden_lessons,
            "hidden_state": self.hidden_state,
            "layer_boost_applied": self.layer_boost_applied,
            "fetch_limit": self.fetch_limit,
            "fallback_fetch_limit": self.fallback_fetch_limit,
            "hydrated_count": self.hydrated_count,
            "get_memory_count": self.get_memory_count,
            "batch_hydration_count": self.batch_hydration_count,
            "cache_hit_count": self.cache_hit_count,
            "cache_miss_count": self.cache_miss_count,
        }
