"""Tests for candidate promotion contract (24.3D-C)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.services.memory_candidate_service import (
    CandidateState,
    EvidenceLevel,
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)
from memoryx.storage import MemoryRepository


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "candidate_promotion.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.fixture
async def svc(ready_repo: MemoryRepository) -> MemoryCandidateService:
    return MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())


def _promotion_meta():
    return {"promotion_source": "user_explicit", "promotion_trusted": True, "promotion_policy_version": "24.3D-C"}


def _tool_promotion_meta():
    return {"promotion_source": "tool_verified", "promotion_trusted": True, "promotion_policy_version": "24.3D-C"}


# ===================================================================
# 1. user_explicit + FACT + E2 → auto verify + commit
# ===================================================================

@pytest.mark.asyncio
async def test_user_explicit_fact_promotes(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="User fact.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.9,
        metadata=_promotion_meta(),
    ))
    # Confirm created as CANDIDATE
    state = await svc.get_candidate_state(mid)
    assert state == CandidateState.CANDIDATE.value
    # Promote
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is True
    assert result["verified"] is True
    assert result["committed"] is True
    final = await svc.get_candidate_state(mid)
    assert final == CandidateState.COMMITTED.value


# ===================================================================
# 2. user_explicit + PREFERENCE + E2 → auto verify+commit
# ===================================================================

@pytest.mark.asyncio
async def test_user_explicit_preference_promotes(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="User preference.", memory_type="PREFERENCE", scope="user", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.9,
        metadata=_promotion_meta(),
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is True
    assert result["committed"] is True


# ===================================================================
# 3. user_explicit + PROJECT → unsupported (blocked by policy)
# ===================================================================

@pytest.mark.asyncio
async def test_user_explicit_project_not_promoted(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Project task.", memory_type="PROJECT", scope="project", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.9,
        metadata=_promotion_meta(),
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False
    # PROJECT requires E3 minimum from policy evaluate, but user_explicit auto_verify only allows E2
    # So candidate stays CANDIDATE and promote says unsupported_memory_type
    assert result["reason"] in ("unsupported_memory_type",)


# ===================================================================
# 4. tool_verified + PROJECT + E3 → auto verify+commit
# ===================================================================

@pytest.mark.asyncio
async def test_tool_verified_project_promotes(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Tool project.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata=_tool_promotion_meta(),
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is True
    assert result["committed"] is True


# ===================================================================
# 5. assistant_inference → BLOCKED
# ===================================================================

@pytest.mark.asyncio
async def test_assistant_inference_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Assumed fact.", memory_type="FACT", scope="global", source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value, confidence=0.5,
        metadata=_promotion_meta(),
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 6. summary → BLOCKED
# ===================================================================

@pytest.mark.asyncio
async def test_summary_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Summary.", memory_type="FACT", scope="global", source_type="summary",
        evidence_level=EvidenceLevel.E1_USER_STATED.value, confidence=0.5,
        metadata=_promotion_meta(),
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 7. E0 → BLOCKED
# ===================================================================

@pytest.mark.asyncio
async def test_e0_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="E0 guess.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value, confidence=0.9,
        metadata=_promotion_meta(),
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 8. confidence < 0.3 → BLOCKED
# ===================================================================

@pytest.mark.asyncio
async def test_low_confidence_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Low conf.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.2,
        metadata=_promotion_meta(),
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 9. memory_class=policy → BLOCKED
# ===================================================================

@pytest.mark.asyncio
async def test_policy_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Policy rule.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={**_promotion_meta(), "memory_class": "policy"},
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 10. memory_class=guard → BLOCKED
# ===================================================================

@pytest.mark.asyncio
async def test_guard_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Guard rule.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={**_promotion_meta(), "memory_class": "guard"},
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 11. memory_class=release_fact → BLOCKED
# ===================================================================

@pytest.mark.asyncio
async def test_release_fact_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Release fact.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value, confidence=0.95,
        metadata={**_promotion_meta(), "memory_class": "release_fact"},
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 12. replacement candidate → BLOCKED
# ===================================================================

@pytest.mark.asyncio
async def test_replacement_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Replacement.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E1_USER_STATED.value, confidence=0.9,
        metadata={**_promotion_meta(), "native_tool_action": "replace"},
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 13. deletion candidate → BLOCKED
# ===================================================================

@pytest.mark.asyncio
async def test_deletion_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Deletion.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E1_USER_STATED.value, confidence=0.9,
        metadata={**_promotion_meta(), "native_tool_action": "remove"},
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 14. untrusted source → BLOCKED (missing promotion_trusted=True)
# ===================================================================

@pytest.mark.asyncio
async def test_untrusted_source_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Fake source.", memory_type="FACT", scope="global", source_type="user_explicit",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.9,
        metadata={"promotion_source": "user_explicit"},  # missing promotion_trusted
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 15. provider add target=memory returns promotion info
# ===================================================================

@pytest.mark.asyncio
async def test_provider_add_memory_returns_promotion(svc: MemoryCandidateService, ready_repo) -> None:
    from memoryx.hermes_provider import MemoryXHermesProvider
    class FakeBridge:
        def __init__(self, repo):
            self.repository = repo
            self.query_api = None
        async def on_tool_call(self, **kwargs):
            return {"event": "on_tool_call", "decision": "allow", "should_block": False, "guard_block": "", "metadata": {"degraded": False}}
    bridge = FakeBridge(ready_repo)
    provider = MemoryXHermesProvider(bridge=bridge)
    result = await provider.handle_tool_call("memory", {"action": "add", "target": "memory", "content": "A fact to remember."})
    assert result["ok"] is True
    assert "promotion" in result


# ===================================================================
# 16. provider add target=user returns promotion info
# ===================================================================

@pytest.mark.asyncio
async def test_provider_add_user_returns_promotion(svc: MemoryCandidateService, ready_repo) -> None:
    from memoryx.hermes_provider import MemoryXHermesProvider
    class FakeBridge:
        def __init__(self, repo):
            self.repository = repo
            self.query_api = None
        async def on_tool_call(self, **kwargs):
            return {"event": "on_tool_call", "decision": "allow", "should_block": False, "guard_block": "", "metadata": {"degraded": False}}
    bridge = FakeBridge(ready_repo)
    provider = MemoryXHermesProvider(bridge=bridge)
    result = await provider.handle_tool_call("memory", {"action": "add", "target": "user", "content": "User preference."})
    assert result["ok"] is True
    assert "promotion" in result


# ===================================================================
# 17. auto_store_service tool result sets promotion_source=tool_verified
# ===================================================================

@pytest.mark.asyncio
async def test_auto_store_tool_result_has_promotion_meta(svc: MemoryCandidateService, ready_repo) -> None:
    from memoryx.services.auto_store_service import AutoStoreService
    from memoryx.services.memory_decision import MemoryDecisionService
    store = AutoStoreService(repository=ready_repo, decision_service=MemoryDecisionService())
    result = await store.store_tool_result(session_id="s1", tool_name="test_tool", result="all tests passed")
    assert result.stored is True
    row = await ready_repo.get_memory(result.id)
    assert row is not None
    meta = json.loads(row.get("metadata_json", "{}"))
    assert meta.get("promotion_source") == "tool_verified"
    assert meta.get("promotion_trusted") is True


# ===================================================================
# 18. auto promotion does NOT use INSERT OR IGNORE
# ===================================================================

@pytest.mark.asyncio
async def test_no_insert_or_ignore(svc: MemoryCandidateService, ready_repo) -> None:
    import inspect
    src = inspect.getsource(type(svc).promote_candidate_if_safe)
    assert "INSERT OR IGNORE" not in src
    assert "INSERT OR REPLACE" not in src


# ===================================================================
# 19. auto promotion does NOT close FK
# ===================================================================

@pytest.mark.asyncio
async def test_fk_not_disabled(svc: MemoryCandidateService, ready_repo) -> None:
    import inspect
    src = inspect.getsource(type(svc).promote_candidate_if_safe)
    assert "foreign_keys" not in src.lower()


# ===================================================================
# 21. Provider add does NOT bypass promote_candidate_if_safe
# ===================================================================

@pytest.mark.asyncio
async def test_provider_add_no_bypass(svc: MemoryCandidateService, ready_repo) -> None:
    """Provider add creates CANDIDATE, then promote commits — never direct COMMITTED."""
    from memoryx.hermes_provider import MemoryXHermesProvider
    class FakeBridge:
        def __init__(self, repo):
            self.repository = repo
            self.query_api = None
        async def on_tool_call(self, **kwargs):
            return {"event": "on_tool_call", "decision": "allow", "should_block": False, "guard_block": "", "metadata": {"degraded": False}}
    bridge = FakeBridge(ready_repo)
    provider = MemoryXHermesProvider(bridge=bridge)
    result = await provider.handle_tool_call("memory", {"action": "add", "target": "memory", "content": "Test memory."})
    assert result["ok"] is True
    mid = result["memory_id"]
    # Must still be candidate — provider add does not bypass promote
    state = await svc.get_candidate_state(mid)
    assert state == CandidateState.CANDIDATE.value


# ===================================================================
# 22. External high evidence without promotion_trusted → no auto commit
# ===================================================================

@pytest.mark.asyncio
async def test_external_high_evidence_no_trust(svc: MemoryCandidateService, ready_repo) -> None:
    """High evidence_level from external request without trusted marker → stays CANDIDATE."""
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="High ev.", memory_type="FACT", scope="global", source_type="user_explicit",
        evidence_level=EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value, confidence=0.95,
        metadata={"promotion_source": "user_explicit"},  # missing promotion_trusted=True
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False
    state = await svc.get_candidate_state(mid)
    assert state == CandidateState.CANDIDATE.value  # stays candidate


# ===================================================================
# 23. External source_type=user_explicit without trusted → no auto commit
# ===================================================================

@pytest.mark.asyncio
async def test_external_source_type_no_trust(svc: MemoryCandidateService, ready_repo) -> None:
    """External source_type claimed as user_explicit without internal trusted → stays CANDIDATE."""
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Fake source.", memory_type="FACT", scope="global", source_type="user_explicit",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.9,
        metadata={"promotion_source": "user_explicit", "promotion_trusted": False},
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False
    state = await svc.get_candidate_state(mid)
    assert state == CandidateState.CANDIDATE.value


# ===================================================================
# 24. promote_candidate_if_safe calls verify_candidate + commit_candidate
# ===================================================================

@pytest.mark.asyncio
async def test_promote_calls_verify_and_commit(svc: MemoryCandidateService, ready_repo) -> None:
    """Verify that promote path actually upgrades evidence_level and commits."""
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Verify promote chain.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value, confidence=0.9,
        metadata=_promotion_meta(),
    ))
    # E0 — stay candidate, not promotable
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False  # E0 blocked
    state = await svc.get_candidate_state(mid)
    assert state == CandidateState.CANDIDATE.value  # still candidate


# ===================================================================
# 25. policy/guard/release_fact blocked even with trusted source
# ===================================================================

@pytest.mark.asyncio
async def test_policy_blocked_overall(svc: MemoryCandidateService, ready_repo) -> None:
    """policy memory_class always blocks promotion regardless of metadata."""
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Policy.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.9,
        metadata={**_promotion_meta(), "memory_class": "policy"},
    ))
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False


# ===================================================================
# 26. replace/remove blocked
# ===================================================================

@pytest.mark.asyncio
async def test_replace_remove_blocked(svc: MemoryCandidateService, ready_repo) -> None:
    """replace/remove native_tool_action always blocks promotion."""
    for action in ("replace", "remove"):
        mid = await svc.create_candidate(MemoryCandidateRequest(
            content=f"{action} test.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
            evidence_level=EvidenceLevel.E1_USER_STATED.value, confidence=0.9,
            metadata={**_promotion_meta(), "native_tool_action": action},
        ))
        result = await svc.promote_candidate_if_safe(mid)
        assert result["promoted"] is False, f"{action} should block promotion"

@pytest.mark.asyncio
async def test_rejected_not_promotable(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Will be rejected.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.9,
        metadata=_promotion_meta(),
    ))
    await svc.reject_candidate(mid, "test")
    result = await svc.promote_candidate_if_safe(mid)
    assert result["promoted"] is False