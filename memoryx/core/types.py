from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ClaimStatus = Literal[
    "candidate",
    "active",
    "superseded",
    "revoked",
    "conflicted",
    "quarantined",
    "expired",
]

ClaimOperation = Literal[
    "create",
    "update",
    "supersede",
    "revoke",
    "conflict",
    "resolve_conflict",
    "reinforce",
    "expire",
]

ConfidenceLabel = Literal["high", "medium", "low", "rejected"]
RetrieverMode = Literal["lite", "hybrid", "vector", "auto"]

@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_type: str
    content: str
    content_hash: str
    created_at: str
    metadata_json: str = "{}"

@dataclass(frozen=True)
class Claim:
    claim_id: str
    claim_type: str
    content: str
    status: ClaimStatus
    confidence: float
    importance: float
    created_at: str
    updated_at: str

@dataclass(frozen=True)
class ClaimVersion:
    version_id: str
    claim_id: str
    operation: ClaimOperation
    before_json: str
    after_json: str
    created_at: str
    reason: str | None = None

@dataclass(frozen=True)
class ScoreBreakdown:
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

@dataclass(frozen=True)
class RetrievalResult:
    claim_id: str
    content: str
    claim_type: str
    status: ClaimStatus
    final_score: float
    confidence_label: ConfidenceLabel
    explanation: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class SearchOptions:
    limit: int = 10
    mode: RetrieverMode = "auto"
    include_inactive: bool = False
    min_score: float = 0.15
    reject_low_confidence: bool = True
    record_access: bool = True
    explain: bool = True
