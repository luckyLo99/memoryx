"""Data types for the Memory Kernel."""

from dataclasses import dataclass, field
from typing import Any

Status = str  # "active" | "superseded" | "revoked"


@dataclass
class Claim:
    """A claim — current active memory node."""

    claim_id: str
    claim_type: str
    content: str
    status: Status = "active"
    confidence: float = 0.5
    importance: float = 0.5
    valid_from: str | None = None
    valid_to: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class Evidence:
    """An evidence event — immutable raw input."""

    evidence_id: str
    source_type: str
    content: str
    content_hash: str
    session_id: str | None = None
    agent_id: str | None = None
    user_id: str | None = None
    metadata_json: str | None = None
    created_at: str | None = None


@dataclass
class ClaimVersion:
    """A version entry tracking every state change on a claim."""

    version_id: str
    claim_id: str
    evidence_ids: list[str] = field(default_factory=list)
    operation: str = "create"
    before_json: dict | None = None
    after_json: dict | None = None
    reason: str | None = None
    created_at: str | None = None


@dataclass
class RetrievalResult:
    """Result of a FTS retrieval query."""

    claim_id: str
    content: str
    score: float
    explanation: dict[str, Any]
