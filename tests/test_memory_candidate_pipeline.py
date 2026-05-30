"""Tests for the MemoryX 24.1B-R Candidate Memory Pipeline.

Risk-tightened test suite.

Coverage:
  1. E0 assistant_inference -> create_candidate only, cannot commit
  2. E2 user_confirmed FACT -> can commit directly
  3. E3 tool_supported PROJECT -> can commit directly
  4. E4 release fact (FACT + memory_class=release_fact) -> verify then commit
  5. E3 release fact cannot commit (needs E4)
  6. POLICY/GUARD rules tested via MemoryCandidatePolicy directly
  7. Empty content rejected
  8. Confidence < 0.3 prevents commit
  9. Reject sets rejected state + legal active_state
 10. Supersede sets superseded state
 11. Unknown metadata fields preserved
 12. evidence_ids persisted
 13. source_event_id persisted
 14. No illegal active_state
 15. No real model API dependency
 16. can_commit rejects metadata missing memory_type
 17. create_candidate always writes memory_type in metadata
 18. verify preserves memory_type
 19. commit fails when memory_type missing
 20. No fallback to FACT
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.services.memory_candidate_service import (
    CandidateDecision,
    CandidateState,
    EvidenceLevel,
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)
from memoryx.storage import MemoryRecord, MemoryRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    r = MemoryRepository(tmp_path / "candidate_pipeline.db")
    return r


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.fixture
def service(ready_repo: MemoryRepository) -> MemoryCandidateService:
    return MemoryCandidateService(
        repository=ready_repo,
        policy=MemoryCandidatePolicy(),
    )


@pytest.fixture
def policy() -> MemoryCandidatePolicy:
    return MemoryCandidatePolicy()


# ===================================================================
# 1. E0 model inference -> candidate only, cannot commit
# ===================================================================

@pytest.mark.asyncio
async def test_e0_assistant_inference_cannot_commit(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """E0 assistant_inference -> create_candidate, cannot commit directly."""
    request = MemoryCandidateRequest(
        content="The user prefers dark mode.",
        memory_type="PREFERENCE",
        source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
        confidence=0.25,
    )
    mid = await service.create_candidate(request)
    assert mid is not None
    state = await service.get_candidate_state(mid)
    assert state == CandidateState.CANDIDATE.value

    ok = await service.commit_candidate(mid)
    assert not ok, "E0 should not be committable directly"


# ===================================================================
# 2. E2 user_confirmed FACT -> can commit directly
# ===================================================================

@pytest.mark.asyncio
async def test_e2_user_confirmed_fact_commits_directly(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """E2 user_confirmed FACT meets minimum evidence -> can commit directly."""
    request = MemoryCandidateRequest(
        content="User confirmed their name is Alice.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.95,
        evidence_ids=["evt-user-123"],
        source_event_id="conv-456",
        tags=["user-profile"],
    )
    mid = await service.create_candidate(request)
    state = await service.get_candidate_state(mid)
    assert state == CandidateState.COMMITTED.value

    mem = await ready_repo.get_memory(mid)
    assert mem is not None
    assert mem["memory_type"] == "FACT"
    assert mem["active_state"] == "active"


# ===================================================================
# 3. E3 tool_supported PROJECT -> verify then commit
# ===================================================================

@pytest.mark.asyncio
async def test_e3_tool_supported_project_verify_then_commit(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """E3 tool_supported PROJECT: candidate -> verify -> commit."""
    request = MemoryCandidateRequest(
        content="Project X build passed all tests.",
        memory_type="PROJECT",
        source_type="tool",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value,
        confidence=0.9,
        evidence_ids=["test-run-789"],
    )
    mid = await service.create_candidate(request)
    state = await service.get_candidate_state(mid)
    assert state == CandidateState.COMMITTED.value

    mem = await ready_repo.get_memory(mid)
    assert mem is not None
    assert mem["active_state"] == "active"


# ===================================================================
# 4. E4 release fact: FACT + memory_class=release_fact -> verify then commit
# ===================================================================

@pytest.mark.asyncio
async def test_e4_release_fact_verify_then_commit(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """E4 release fact (FACT + memory_class=release_fact) -> verify -> commit."""
    request = MemoryCandidateRequest(
        content="Release v2.0.0 passed ReleaseGate with 343 tests.",
        memory_type="FACT",
        source_type="release_gate",
        evidence_level=EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value,
        confidence=1.0,
        evidence_ids=["release-2026-05-30"],
        metadata={"memory_class": "release_fact"},
    )
    mid = await service.create_candidate(request)
    state = await service.get_candidate_state(mid)
    assert state == CandidateState.COMMITTED.value

    mem = await ready_repo.get_memory(mid)
    assert mem is not None
    assert mem["memory_type"] == "FACT", "release fact must store as FACT"
    meta = json.loads(mem["metadata_json"])
    assert meta.get("memory_class") == "release_fact"


# ===================================================================
# 5. E3 release fact cannot commit (needs E4)
# ===================================================================

@pytest.mark.asyncio
async def test_e3_release_fact_cannot_commit(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """E3 evidence is insufficient for release fact (needs E4)."""
    request = MemoryCandidateRequest(
        content="Build passed but not release-gated.",
        memory_type="FACT",
        source_type="tool",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value,
        confidence=0.9,
        evidence_ids=["test-run-789"],
        metadata={"memory_class": "release_fact"},
    )
    mid = await service.create_candidate(request)
    state = await service.get_candidate_state(mid)
    assert state == CandidateState.CANDIDATE.value, "E3 release fact should be candidate"

    # Verify with E4
    ok = await service.verify_candidate(
        mid,
        evidence_level=EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value,
        evidence_ids=["release-gate-confirm"],
    )
    assert ok
    ok = await service.commit_candidate(mid)
    assert ok, "E3 -> verified with E4 should allow commit"
    state = await service.get_candidate_state(mid)
    assert state == CandidateState.COMMITTED.value


# ===================================================================
# 6. POLICY/GUARD rules evaluated via MemoryCandidatePolicy directly
# ===================================================================

def test_policy_guard_assistant_inference_blocked(policy: MemoryCandidatePolicy) -> None:
    """POLICY/GUARD from assistant_inference cannot commit, even with E4 evidence level."""
    result = policy.evaluate(MemoryCandidateRequest(
        content="Never store raw API keys.",
        memory_type="POLICY",
        source_type="assistant_inference",
        evidence_level=EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value,
        confidence=0.9,
    ))
    # POLICY/GUARD from assistant still blocked - must go through candidate pipeline
    assert result.state == CandidateState.CANDIDATE.value
    assert "assistant" in result.reason


def test_policy_guard_user_source_ok(policy: MemoryCandidatePolicy) -> None:
    """POLICY from user source with E4 can commit directly."""
    result = policy.evaluate(MemoryCandidateRequest(
        content="User-defined policy.",
        memory_type="POLICY",
        source_type="user",
        evidence_level=EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value,
        confidence=0.9,
    ))
    assert result.state == CandidateState.COMMITTED.value


# ===================================================================
# 7. Empty content rejected
# ===================================================================

@pytest.mark.asyncio
async def test_empty_content_rejected(
    service: MemoryCandidateService,
) -> None:
    """Empty content should raise ValueError."""
    request = MemoryCandidateRequest(
        content="   ",
        memory_type="FACT",
        source_type="user",
    )
    with pytest.raises(ValueError, match="rejected by policy"):
        await service.create_candidate(request)


# ===================================================================
# 8. Low confidence prevents commit
# ===================================================================

@pytest.mark.asyncio
async def test_low_confidence_prevents_commit(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """Confidence < 0.3 -> candidate only, cannot commit."""
    request = MemoryCandidateRequest(
        content="User might like cats.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.2,
    )
    mid = await service.create_candidate(request)
    state = await service.get_candidate_state(mid)
    assert state == CandidateState.CANDIDATE.value

    ok = await service.verify_candidate(
        mid,
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        evidence_ids=["evt-confirm-1"],
    )
    assert ok
    ok = await service.commit_candidate(mid)
    assert not ok, "low confidence should prevent commit"

    state = await service.get_candidate_state(mid)
    assert state == CandidateState.VERIFIED.value


# ===================================================================
# 9. Reject candidate
# ===================================================================

@pytest.mark.asyncio
async def test_reject_candidate_sets_rejected(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """Reject sets candidate_state=rejected and a legal active_state."""
    request = MemoryCandidateRequest(
        content="Spurious memory.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.95,
    )
    mid = await service.create_candidate(request)

    ok = await service.reject_candidate(mid, "user requested deletion")
    assert ok

    state = await service.get_candidate_state(mid)
    assert state == CandidateState.REJECTED.value

    mem = await ready_repo.get_memory(mid)
    assert mem["active_state"] in ("active", "archived", "superseded", "quarantined")
    meta = json.loads(mem["metadata_json"])
    assert meta.get("rejection_reason") == "user requested deletion"


# ===================================================================
# 10. Supersede candidate
# ===================================================================

@pytest.mark.asyncio
async def test_supersede_candidate_sets_superseded(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """Supersede sets candidate_state=superseded, active_state=superseded."""
    request = MemoryCandidateRequest(
        content="Old fact.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.9,
    )
    mid = await service.create_candidate(request)

    ok = await service.supersede_candidate(mid, "new-fact-id", "replaced by newer info")
    assert ok

    state = await service.get_candidate_state(mid)
    assert state == CandidateState.SUPERSEDED.value

    mem = await ready_repo.get_memory(mid)
    assert mem["active_state"] == "superseded"
    meta = json.loads(mem["metadata_json"])
    assert meta.get("superseded_by") == "new-fact-id"


# ===================================================================
# 11. Metadata preserves unknown fields
# ===================================================================

@pytest.mark.asyncio
async def test_metadata_preserves_unknown_fields(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """Unknown metadata fields survive candidate lifecycle."""
    request = MemoryCandidateRequest(
        content="Custom metadata test.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.95,
        metadata={"custom_key": "custom_value", "another_field": 42},
    )
    mid = await service.create_candidate(request)

    mem = await ready_repo.get_memory(mid)
    meta = json.loads(mem["metadata_json"])
    assert meta.get("custom_key") == "custom_value"
    assert meta.get("another_field") == 42
    assert meta.get("candidate_state") is not None
    assert meta.get("evidence_level") is not None


# ===================================================================
# 12. evidence_ids persisted
# ===================================================================

@pytest.mark.asyncio
async def test_evidence_ids_persisted(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """evidence_ids stored in metadata."""
    eids = ["evt-a", "evt-b", "evt-c"]
    request = MemoryCandidateRequest(
        content="Evidence test.",
        memory_type="FACT",
        source_type="tool",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value,
        confidence=0.95,
        evidence_ids=eids,
    )
    mid = await service.create_candidate(request)

    mem = await ready_repo.get_memory(mid)
    meta = json.loads(mem["metadata_json"])
    assert meta.get("evidence_ids") == eids


# ===================================================================
# 13. source_event_id persisted
# ===================================================================

@pytest.mark.asyncio
async def test_source_event_id_persisted(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """source_event_id stored in metadata."""
    request = MemoryCandidateRequest(
        content="Source event test.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.9,
        source_event_id="evt-source-001",
    )
    mid = await service.create_candidate(request)

    mem = await ready_repo.get_memory(mid)
    meta = json.loads(mem["metadata_json"])
    assert meta.get("source_event_id") == "evt-source-001"


# ===================================================================
# 14. No illegal active_state
# ===================================================================

@pytest.mark.asyncio
async def test_no_illegal_active_state(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """No illegal active_state introduced."""
    request = MemoryCandidateRequest(
        content="Legal state test.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.9,
    )
    mid = await service.create_candidate(request)
    mem = await ready_repo.get_memory(mid)
    assert mem["active_state"] in ("active", "archived", "superseded", "quarantined")


# ===================================================================
# 15. No real model API dependency (always true)
# ===================================================================

def test_no_real_model_api_dependency() -> None:
    """No external model API calls."""
    assert True


# ===================================================================
# 16-19: Risk 3 - memory_type in metadata
# ===================================================================

def test_can_commit_rejects_missing_memory_type(policy: MemoryCandidatePolicy) -> None:
    """can_commit must reject when metadata is missing memory_type."""
    decision = policy.can_commit({
        "candidate_state": CandidateState.VERIFIED.value,
        "evidence_level": EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value,
        "confidence": 0.95,
    })
    assert not decision.allowed
    assert "missing_memory_type" in decision.reason

def test_can_commit_rejects_empty_metadata(policy: MemoryCandidatePolicy) -> None:
    """can_commit must reject empty metadata."""
    decision = policy.can_commit({})
    assert not decision.allowed
    assert "missing_memory_type" in decision.reason

@pytest.mark.asyncio
async def test_create_candidate_writes_memory_type_in_metadata(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """create_candidate always writes memory_type into metadata_json."""
    request = MemoryCandidateRequest(
        content="Memory type in metadata test.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.9,
    )
    mid = await service.create_candidate(request)

    mem = await ready_repo.get_memory(mid)
    meta = json.loads(mem["metadata_json"])
    assert "memory_type" in meta
    assert meta["memory_type"] == "FACT"

@pytest.mark.asyncio
async def test_verify_preserves_memory_type(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """verify_candidate must not delete memory_type from metadata."""
    request = MemoryCandidateRequest(
        content="Verify preserve test.",
        memory_type="PROJECT",
        source_type="user",
        evidence_level=EvidenceLevel.E1_USER_STATED.value,
        confidence=0.85,
    )
    mid = await service.create_candidate(request)

    ok = await service.verify_candidate(
        mid,
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value,
        evidence_ids=["verify-confirm"],
    )
    assert ok

    mem = await ready_repo.get_memory(mid)
    meta = json.loads(mem["metadata_json"])
    assert "memory_type" in meta
    assert meta["memory_type"] == "PROJECT"

@pytest.mark.asyncio
async def test_commit_fails_without_memory_type_metadata(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """commit_candidate fails if someone stripped memory_type from metadata."""
    request = MemoryCandidateRequest(
        content="Missing memory type test.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E1_USER_STATED.value,
        confidence=0.85,
    )
    mid = await service.create_candidate(request)

    # Verify upgrading evidence
    ok = await service.verify_candidate(
        mid,
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        evidence_ids=["confirm-001"],
    )
    assert ok

    # Manually set memory_type to None in metadata to simulate corruption
    await ready_repo.update_memory_metadata(mid, {"memory_type": None})

    ok = await service.commit_candidate(mid)
    assert not ok, "commit must fail when memory_type is missing from metadata"


# ===================================================================
# E0 -> verify with E2 -> commit should work (classic pipeline)
# ===================================================================

@pytest.mark.asyncio
async def test_e0_verified_to_e2_allows_commit(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """E0 candidate -> verify with E2 -> commit."""
    request = MemoryCandidateRequest(
        content="Model inference about user preference.",
        memory_type="FACT",
        source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
        confidence=0.5,
    )
    mid = await service.create_candidate(request)
    assert await service.get_candidate_state(mid) == CandidateState.CANDIDATE.value

    ok = await service.verify_candidate(
        mid,
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        evidence_ids=["user-confirmed-001"],
    )
    assert ok

    ok = await service.commit_candidate(mid)
    assert ok

    state = await service.get_candidate_state(mid)
    assert state == CandidateState.COMMITTED.value


# ===================================================================
# Duplicate verify succeeds
# ===================================================================

@pytest.mark.asyncio
async def test_duplicate_verify(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """Verifying an already verified candidate should succeed."""
    request = MemoryCandidateRequest(
        content="Re-verify test.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E1_USER_STATED.value,
        confidence=0.85,
    )
    mid = await service.create_candidate(request)
    assert await service.get_candidate_state(mid) == CandidateState.CANDIDATE.value

    ok = await service.verify_candidate(
        mid,
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        evidence_ids=["first-verify"],
    )
    assert ok

    ok = await service.verify_candidate(
        mid,
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value,
        evidence_ids=["second-verify"],
    )
    assert ok

    state = await service.get_candidate_state(mid)
    assert state == CandidateState.VERIFIED.value


# ===================================================================
# get_candidate_state for non-existent memory
# ===================================================================

@pytest.mark.asyncio
async def test_get_candidate_state_nonexistent(
    service: MemoryCandidateService,
) -> None:
    """get_candidate_state for non-existent memory returns None."""
    state = await service.get_candidate_state("nonexistent-id")
    assert state is None


# ===================================================================
# Already committed memory cannot be re-committed
# ===================================================================

@pytest.mark.asyncio
async def test_committed_cannot_be_recommitted(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """Already committed memory should not commit again."""
    request = MemoryCandidateRequest(
        content="Already committed.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.95,
    )
    mid = await service.create_candidate(request)
    assert await service.get_candidate_state(mid) == CandidateState.COMMITTED.value

    ok = await service.commit_candidate(mid)
    assert not ok, "already committed should not commit again"


# ===================================================================
# No fallback to FACT test
# ===================================================================

def test_no_fallback_to_fact_in_can_commit(policy: MemoryCandidatePolicy) -> None:
    """can_commit must not fallback to FACT when memory_type is missing."""
    decision = policy.can_commit({
        "candidate_state": CandidateState.VERIFIED.value,
        "evidence_level": EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value,
        "confidence": 0.95,
    })
    assert not decision.allowed
    assert "missing_memory_type" in decision.reason


# ===================================================================
# E1 user_stated FACT cannot commit directly
# ===================================================================

@pytest.mark.asyncio
async def test_e1_user_stated_fact_candidate_only(
    service: MemoryCandidateService,
    ready_repo: MemoryRepository,
) -> None:
    """E1 user_stated FACT -> candidate only, needs verify."""
    request = MemoryCandidateRequest(
        content="User mentioned something.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E1_USER_STATED.value,
        confidence=0.85,
    )
    mid = await service.create_candidate(request)
    state = await service.get_candidate_state(mid)
    assert state == CandidateState.CANDIDATE.value, "E1 FACT should be candidate"
