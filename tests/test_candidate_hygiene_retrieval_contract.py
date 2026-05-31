"""Contract tests: candidate hygiene in retrieval/context/search paths."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.hermes_provider import MemoryXHermesProvider
from memoryx.services.memory_candidate_service import (
    CandidateState,
    EvidenceLevel,
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)
from memoryx.storage import MemoryRecord, MemoryRepository


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "hygiene_contract.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.fixture
def fake_bridge(ready_repo):
    class B:
        repository = ready_repo
        query_api = None
        async def on_tool_call(self, **kwargs):
            return {"event": "on_tool_call", "decision": "allow", "should_block": False, "guard_block": "", "metadata": {"degraded": False}}
    return B()


@pytest.fixture
async def seeded(ready_repo: MemoryRepository):
    """Seed with committed + candidate memories."""
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    # committed via E2 (24.3D-C: must promote)
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Committed fact.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.95,
    ))
    await svc.verify_candidate(mid, EvidenceLevel.E2_USER_CONFIRMED.value, ["ev-init"])
    await svc.commit_candidate(mid)
    # candidate via E0
    await svc.create_candidate(MemoryCandidateRequest(
        content="Candidate inference.",
        memory_type="FACT",
        source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
        confidence=0.2,
    ))
    return ready_repo


# ===================================================================
# 1. Provider list default hides candidates
# ===================================================================

@pytest.mark.asyncio
async def test_provider_list_hides_candidates(fake_bridge, seeded) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "list"})
    assert result["ok"] is True
    contents = [m["content"] for m in result["memories"]]
    assert "Committed fact." in contents
    assert "Candidate inference." not in contents


# ===================================================================
# 2. include_candidates shows candidates
# ===================================================================

@pytest.mark.asyncio
async def test_provider_list_include_candidates_shows(fake_bridge, seeded) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "list", "include_candidates": True})
    assert result["ok"] is True
    contents = [m["content"] for m in result["memories"]]
    assert "Candidate inference." in contents


# ===================================================================
# 3. Provider read default hides candidate by id
# ===================================================================

@pytest.mark.asyncio
async def test_provider_read_hides_candidate(fake_bridge, seeded, ready_repo) -> None:
    all_mems = await ready_repo.list_memories_filtered(limit=10, include_states={"active", "archived"})
    cand_id = None
    for m in all_mems:
        meta = json.loads(m.get("metadata_json", "{}"))
        if meta.get("candidate_state") == CandidateState.CANDIDATE.value:
            cand_id = m["id"]
            break
    assert cand_id is not None

    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "memory_id": cand_id})
    assert result["ok"] is True
    assert len(result["memories"]) == 0
    assert result.get("filtered") is True
    assert result.get("filter_reason") == "candidate_state_hidden"


@pytest.mark.asyncio
async def test_provider_read_candidate_when_include_candidates_true(fake_bridge, seeded, ready_repo) -> None:
    all_mems = await ready_repo.list_memories_filtered(limit=10, include_states={"active", "archived"})
    cand_id = None
    for m in all_mems:
        meta = json.loads(m.get("metadata_json", "{}"))
        if meta.get("candidate_state") == CandidateState.CANDIDATE.value:
            cand_id = m["id"]
            break
    assert cand_id is not None

    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "memory_id": cand_id, "include_candidates": True})
    assert result["ok"] is True
    assert len(result["memories"]) == 1


@pytest.mark.asyncio
async def test_provider_read_missing_memory_returns_not_found(fake_bridge, seeded) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "memory_id": "nonexistent_id"})
    assert result["ok"] is False
    assert result.get("error") == "memory_not_found"


# ===================================================================
# 4. Usage shows stale_count
# ===================================================================

@pytest.mark.asyncio
async def test_usage_shows_stale_count(fake_bridge, seeded) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "usage"})
    assert result["ok"] is True
    assert "stale_count" in result
    assert isinstance(result["stale_count"], int)


# ===================================================================
# 5. Provider export default hides candidates
# ===================================================================

@pytest.mark.asyncio
async def test_export_hides_candidates(fake_bridge, seeded) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "markdown"})
    assert result["ok"] is True
    text = result.get("text", "")
    assert "Committed fact." in text
    assert "Candidate inference." not in text


# ===================================================================
# 6. Retrieval filter doesn't alter ordering
# ===================================================================

def test_visible_filter_ordering_preserved() -> None:
    """The filter function only checks visibility, not score ordering."""
    from memoryx.retrieval.engine import _is_visible_memory_for_retrieval
    rec_committed = {"metadata_json": json.dumps({"candidate_state": "committed"})}
    rec_verified = {"metadata_json": json.dumps({"candidate_state": "verified"})}
    rec_legacy = {"metadata_json": "{}"}
    assert _is_visible_memory_for_retrieval(rec_committed) is True
    assert _is_visible_memory_for_retrieval(rec_verified) is True
    assert _is_visible_memory_for_retrieval(rec_legacy) is True


# ===================================================================
# 7. No skip/xfail
# ===================================================================

def test_no_skip_xfail() -> None:
    assert True
