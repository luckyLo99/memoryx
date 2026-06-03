"""MemoryX services package.

Exports the top-level service classes, with lazy imports for heavy
dependencies and optional LLM clients.
"""
from __future__ import annotations

from .memory_candidate_service import (
    CandidateDecision,
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)
from .auto_store_service import AutoStoreResult, AutoStoreService

__all__ = [
    "AutoStoreResult",
    "AutoStoreService",
    "CandidateDecision",
    "MemoryCandidatePolicy",
    "MemoryCandidateRequest",
    "MemoryCandidateService",
]
