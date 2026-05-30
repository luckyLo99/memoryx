"""MemoryX 24.1B: Candidate Memory Pipeline

candidate -> verify -> commit -> reject / supersede

Stores candidate state in metadata_json to avoid schema changes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from memoryx.storage import MemoryRecord


# ---------------------------------------------------------------------------
# Evidence levels
# ---------------------------------------------------------------------------

class EvidenceLevel(str, Enum):
    E0_MODEL_INFERENCE = "E0_MODEL_INFERENCE"
    E1_USER_STATED = "E1_USER_STATED"
    E2_USER_CONFIRMED = "E2_USER_CONFIRMED"
    E3_TOOL_OR_TEST_SUPPORTED = "E3_TOOL_OR_TEST_SUPPORTED"
    E4_RELEASE_GATE_SUPPORTED = "E4_RELEASE_GATE_SUPPORTED"


# ---------------------------------------------------------------------------
# Candidate states
# ---------------------------------------------------------------------------

class CandidateState(str, Enum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    COMMITTED = "committed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


# ---------------------------------------------------------------------------
# Memory write risk
# ---------------------------------------------------------------------------

class MemoryWriteRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------------------------------------------------------------------------
# Request / Decision dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MemoryCandidateRequest:
    content: str
    session_id: str | None = None
    memory_type: str = "FACT"
    scope: str = "session"
    source_type: str = "unknown"
    source_event_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    evidence_level: str = EvidenceLevel.E0_MODEL_INFERENCE.value
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


@dataclass
class CandidateDecision:
    allowed: bool
    state: str
    reason: str
    required_evidence_level: str
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Candidate metadata keys (written into metadata_json)
# ---------------------------------------------------------------------------

_CANDIDATE_META_KEYS = frozenset({
    "candidate_state",
    "evidence_level",
    "source_type",
    "source_event_id",
    "evidence_ids",
    "confidence",
    "verified_at",
    "committed_at",
    "rejection_reason",
    "superseded_by",
    "superseded_at",
})


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

class MemoryCandidatePolicy:
    """Policy rules for candidate memory lifecycle."""

    @staticmethod
    def _is_release_fact(memory_type: str, metadata: dict | None) -> bool:
        """Check if this is a release fact expressed as FACT + metadata marker."""
        if memory_type != "FACT":
            return False
        if metadata is None:
            return False
        return (
            metadata.get("memory_class") == "release_fact"
            or metadata.get("fact_subtype") == "release_fact"
        )

    @staticmethod
    def required_evidence_level(
        memory_type: str, scope: str, source_type: str,
        metadata: dict | None = None,
    ) -> str:
        """Return the minimum evidence level required for this combination.

        Release facts are identified by memory_type="FACT" combined with
        metadata memory_class/fact_subtype, not a separate memory_type.
        """
        # release fact: FACT + memory_class marker -> E4
        if MemoryCandidatePolicy._is_release_fact(memory_type, metadata):
            return EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value

        if memory_type in ("FACT", "PREFERENCE"):
            return EvidenceLevel.E2_USER_CONFIRMED.value
        if memory_type in ("PROJECT", "TASK", "LESSON"):
            return EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value
        if memory_type in ("POLICY", "RULE", "GUARD"):
            if source_type in ("assistant_inference", "assistant", "summary"):
                # POLICY/GUARD cannot originate from assistant-level sources
                return EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value
            return EvidenceLevel.E2_USER_CONFIRMED.value
        # Default for unknown types
        return EvidenceLevel.E1_USER_STATED.value

    @staticmethod
    def evaluate(request: MemoryCandidateRequest) -> CandidateDecision:
        """Evaluate a candidate request against policy rules."""
        warnings: list[str] = []

        # Rule 7: empty content
        if not request.content or not request.content.strip():
            return CandidateDecision(
                allowed=False,
                state=CandidateState.REJECTED.value,
                reason="content is empty",
                required_evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
                warnings=["empty content is never allowed"],
            )

        required = MemoryCandidatePolicy.required_evidence_level(
            request.memory_type, request.scope, request.source_type,
            metadata=request.metadata,
        )

        # Rule 5: E0 cannot be committed
        if request.evidence_level == EvidenceLevel.E0_MODEL_INFERENCE.value:
            return CandidateDecision(
                allowed=True,
                state=CandidateState.CANDIDATE.value,
                reason="E0 model inference: can only be candidate, not committed",
                required_evidence_level=required,
                warnings=["E0 model inference requires verification before commit"],
            )

        # Rule 6: assistant source with low evidence cannot commit directly
        if request.source_type in ("assistant", "assistant_inference", "summary"):
            # Risk tightening: POLICY/RULE/GUARD from assistant never commits directly
            if request.memory_type in ("POLICY", "RULE", "GUARD"):
                return CandidateDecision(
                    allowed=True,
                    state=CandidateState.CANDIDATE.value,
                    reason=f"{request.memory_type} from {request.source_type}: must go through verify pipeline",
                    required_evidence_level=required,
                    warnings=[f"{request.memory_type} from assistant source cannot commit directly"],
                )
            evidence_order = _evidence_order()
            req_order = evidence_order.get(required, 0)
            ev_order = evidence_order.get(request.evidence_level, 0)
            if ev_order < req_order:
                return CandidateDecision(
                    allowed=True,
                    state=CandidateState.CANDIDATE.value,
                    reason=f"{request.source_type} source needs {required}, got {request.evidence_level}",
                    required_evidence_level=required,
                    warnings=[f"evidence {request.evidence_level} below required {required}"],
                )

        # Rule 8: low confidence
        if request.confidence < 0.3:
            # Low confidence: can only be candidate, not committed
            return CandidateDecision(
                allowed=True,
                state=CandidateState.CANDIDATE.value,
                reason=f"confidence {request.confidence} < 0.3: can only be candidate",
                required_evidence_level=required,
                warnings=[f"low confidence ({request.confidence}): requires verification"],
            )

        # Check general evidence requirement
        evidence_order = _evidence_order()
        req_order = evidence_order.get(required, 0)
        ev_order = evidence_order.get(request.evidence_level, 0)

        if ev_order < req_order:
            return CandidateDecision(
                allowed=True,
                state=CandidateState.CANDIDATE.value,
                reason=f"evidence {request.evidence_level} below required {required}",
                required_evidence_level=required,
                warnings=[f"evidence {request.evidence_level} below required {required}"],
            )

        return CandidateDecision(
            allowed=True,
            state=CandidateState.COMMITTED.value,
            reason="all policy checks passed, can commit directly",
            required_evidence_level=required,
            warnings=warnings,
        )

    @staticmethod
    def can_commit(metadata: dict) -> CandidateDecision:
        """Check if the metadata allows transitioning to committed."""
        # Risk 3: reject if memory_type is missing from metadata
        if "memory_type" not in metadata or not metadata.get("memory_type"):
            return CandidateDecision(
                allowed=False,
                state=metadata.get("candidate_state", CandidateState.CANDIDATE.value),
                reason="missing_memory_type: metadata has no memory_type field",
                required_evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
                warnings=["memory_type is required in metadata for commit"],
            )

        state = metadata.get("candidate_state", CandidateState.CANDIDATE.value)
        evidence_level = metadata.get("evidence_level", EvidenceLevel.E0_MODEL_INFERENCE.value)
        confidence = metadata.get("confidence", 0.0)
        source_type = metadata.get("source_type", "unknown")
        memory_type = metadata["memory_type"]

        warnings: list[str] = []

        # Must be in verified state to commit
        if state not in (CandidateState.VERIFIED.value, CandidateState.CANDIDATE.value):
            return CandidateDecision(
                allowed=False,
                state=state,
                reason=f"cannot commit from state '{state}': must be 'verified' or 'candidate'",
                required_evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
                warnings=["wrong state for commit"],
            )

        # E0 cannot be committed
        if evidence_level == EvidenceLevel.E0_MODEL_INFERENCE.value:
            return CandidateDecision(
                allowed=False,
                state=state,
                reason="E0 evidence cannot be committed directly",
                required_evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
                warnings=["E0 model inference cannot be committed"],
            )

        # Low confidence check
        if confidence < 0.3:
            return CandidateDecision(
                allowed=False,
                state=state,
                reason=f"confidence {confidence} < 0.3, cannot commit",
                required_evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
                warnings=[f"low confidence ({confidence}) prevents commit"],
            )

        # Check evidence level requirement
        required = MemoryCandidatePolicy.required_evidence_level(
            memory_type, "global", source_type, metadata=metadata,
        )
        evidence_order = _evidence_order()
        req_order = evidence_order.get(required, 0)
        ev_order = evidence_order.get(evidence_level, 0)

        if ev_order < req_order:
            return CandidateDecision(
                allowed=False,
                state=state,
                reason=f"evidence {evidence_level} below required {required} for commit",
                required_evidence_level=required,
                warnings=[f"evidence {evidence_level} below required {required}"],
            )

        return CandidateDecision(
            allowed=True,
            state=CandidateState.COMMITTED.value,
            reason="all commit checks passed",
            required_evidence_level=required,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MemoryCandidateService:
    """Candidate memory pipeline: candidate -> verify -> commit / reject / supersede."""

    def __init__(self, repository: Any, policy: MemoryCandidatePolicy | None = None) -> None:
        self.repository = repository
        self.policy = policy or MemoryCandidatePolicy()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_candidate_metadata(self, request: MemoryCandidateRequest) -> dict[str, Any]:
        return {
            "candidate_state": CandidateState.CANDIDATE.value,
            "memory_type": request.memory_type,
            "evidence_level": request.evidence_level,
            "source_type": request.source_type,
            "source_event_id": request.source_event_id,
            "evidence_ids": list(request.evidence_ids),
            "confidence": request.confidence,
            "verified_at": None,
            "committed_at": None,
            "rejection_reason": None,
            "superseded_by": None,
            "superseded_at": None,
        }

    def _merge_metadata(self, existing: dict | str, patch: dict) -> str:
        """Merge patch into existing metadata, preserving unknown fields."""
        if isinstance(existing, str):
            try:
                existing_dict = json.loads(existing) if existing else {}
            except (json.JSONDecodeError, ValueError):
                existing_dict = {"_metadata_repair_warning": "metadata_json was not valid JSON, reset to {}"}
        elif isinstance(existing, dict):
            existing_dict = dict(existing)
        else:
            existing_dict = {}
        existing_dict.update(patch)
        return json.dumps(existing_dict, ensure_ascii=False)

    async def create_candidate(self, request: MemoryCandidateRequest) -> str:
        """Create a candidate memory. Always writes candidate_state='candidate' in metadata."""
        decision = self.policy.evaluate(request)
        if not decision.allowed:
            raise ValueError(f"candidate rejected by policy: {decision.reason}")

        # Merge request.metadata with candidate metadata (request.metadata wins)
        candidate_meta = self._build_candidate_metadata(request)
        merged = dict(candidate_meta)
        merged.update(request.metadata)

        # Build the MemoryRecord
        record = MemoryRecord(
            memory_type=request.memory_type,
            content=request.content.strip(),
            session_id=request.session_id,
            scope=request.scope,
            metadata_json=json.dumps(merged, ensure_ascii=False),
            tags_json=json.dumps(request.tags, ensure_ascii=False),
            entities_json=json.dumps(request.entities, ensure_ascii=False),
        )

        # Set state per decision
        if decision.state == CandidateState.COMMITTED.value:
            record.active_state = "active"
            merged["candidate_state"] = CandidateState.COMMITTED.value
            merged["committed_at"] = self._now_iso()
            record.metadata_json = json.dumps(merged, ensure_ascii=False)
        else:
            record.active_state = "active"
            record.metadata_json = json.dumps(merged, ensure_ascii=False)

        memory_id = await self.repository.store_memory(record)
        return memory_id

    async def verify_candidate(
        self, memory_id: str, evidence_level: str, evidence_ids: list[str],
        verified_by: str = "system",
    ) -> bool:
        """Transition candidate state to verified."""
        memory = await self.repository.get_memory(memory_id)
        if memory is None:
            return False

        metadata = self._parse_metadata(memory.get("metadata_json", "{}"))
        current_state = metadata.get("candidate_state", CandidateState.CANDIDATE.value)

        if current_state not in (CandidateState.CANDIDATE.value, CandidateState.VERIFIED.value):
            return False  # can only verify from candidate or re-verify

        now = self._now_iso()
        patch = {
            "candidate_state": CandidateState.VERIFIED.value,
            "evidence_level": evidence_level,
            "evidence_ids": list(evidence_ids),
            "verified_at": now,
        }
        return await self.repository.update_memory_metadata(memory_id, patch)

    async def commit_candidate(self, memory_id: str) -> bool:
        """Commit a verified candidate to active memory."""
        memory = await self.repository.get_memory(memory_id)
        if memory is None:
            return False

        metadata = self._parse_metadata(memory.get("metadata_json", "{}"))
        decision = self.policy.can_commit(metadata)
        if not decision.allowed:
            return False

        now = self._now_iso()
        patch = {
            "candidate_state": CandidateState.COMMITTED.value,
            "committed_at": now,
        }
        meta_ok = await self.repository.update_memory_metadata(memory_id, patch)
        state_ok = await self.repository.update_memory_active_state(memory_id, "active")
        return meta_ok and state_ok

    async def reject_candidate(self, memory_id: str, reason: str) -> bool:
        """Reject a candidate. Uses 'quarantined' or 'archived' active_state."""
        memory = await self.repository.get_memory(memory_id)
        if memory is None:
            return False

        now = self._now_iso()
        patch = {
            "candidate_state": CandidateState.REJECTED.value,
            "rejection_reason": reason,
        }
        meta_ok = await self.repository.update_memory_metadata(memory_id, patch)

        # Use existing legal active_state: prefer 'quarantined', fallback to 'archived'
        active = memory.get("active_state", "active")
        if active == "active":
            state_ok = await self.repository.update_memory_active_state(memory_id, "quarantined")
        else:
            state_ok = await self.repository.update_memory_active_state(memory_id, active)
        return meta_ok and state_ok

    async def supersede_candidate(self, memory_id: str, superseded_by: str, reason: str) -> bool:
        """Supersede a candidate with a newer memory."""
        memory = await self.repository.get_memory(memory_id)
        if memory is None:
            return False

        now = self._now_iso()
        patch = {
            "candidate_state": CandidateState.SUPERSEDED.value,
            "superseded_by": superseded_by,
            "superseded_at": now,
        }
        meta_ok = await self.repository.update_memory_metadata(memory_id, patch)
        state_ok = await self.repository.update_memory_active_state(memory_id, "superseded")
        return meta_ok and state_ok

    async def get_candidate_state(self, memory_id: str) -> str | None:
        """Return the candidate state string, or None if not found."""
        memory = await self.repository.get_memory(memory_id)
        if memory is None:
            return None
        metadata = self._parse_metadata(memory.get("metadata_json", "{}"))
        return metadata.get("candidate_state")

    @staticmethod
    def _parse_metadata(metadata_json: str) -> dict[str, Any]:
        try:
            return json.loads(metadata_json) if metadata_json else {}
        except (json.JSONDecodeError, ValueError):
            return {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _evidence_order() -> dict[str, int]:
    return {
        EvidenceLevel.E0_MODEL_INFERENCE.value: 0,
        EvidenceLevel.E1_USER_STATED.value: 1,
        EvidenceLevel.E2_USER_CONFIRMED.value: 2,
        EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value: 3,
        EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value: 4,
    }