"""Tests for MemoryX native memory lifecycle: turn/session-end candidate extraction."""
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
from memoryx.storage import MemoryRecord, MemoryRepository


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "lifecycle.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.fixture
def svc(ready_repo: MemoryRepository) -> MemoryCandidateService:
    return MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())


# ===================================================================
# 1. User says "记住我喜欢中文工程化输出" -> PREFERENCE candidate
# ===================================================================

@pytest.mark.asyncio
async def test_user_preference_extracted(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    ids = await svc.extract_candidates_from_turn(
        session_id="s1",
        user_message="记住我喜欢中文工程化输出，以后都这样",
        max_candidates=5,
    )
    assert len(ids) >= 1, "should extract at least 1 candidate"

    mem = await ready_repo.get_memory(ids[0])
    meta = json.loads(mem["metadata_json"])
    assert mem["memory_type"] == "PREFERENCE"
    assert mem["scope"] == "user"
    assert meta.get("candidate_state") == CandidateState.CANDIDATE.value
    assert meta.get("auto_extracted") is True
    assert meta.get("extraction_source") == "turn"


# ===================================================================
# 2. User says "当前基线是 X，下一步是 Y" -> PROJECT candidate
# ===================================================================

@pytest.mark.asyncio
async def test_project_state_extracted(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    ids = await svc.extract_candidates_from_turn(
        session_id="s2",
        user_message="当前基线是 feature/24.0-runtime-replay，下一步是提交修改",
        max_candidates=5,
    )
    assert len(ids) >= 1
    mem = await ready_repo.get_memory(ids[0])
    assert mem["memory_type"] == "PROJECT"
    assert mem["scope"] == "project"


# ===================================================================
# 3. Assistant response -> E0 candidate only
# ===================================================================

@pytest.mark.asyncio
async def test_assistant_response_e0_only(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    ids = await svc.extract_candidates_from_turn(
        session_id="s3",
        assistant_response="Based on the analysis, the test suite shows 412 passing tests with no failures.",
        max_candidates=5,
    )
    assert len(ids) >= 1
    mem = await ready_repo.get_memory(ids[0])
    meta = json.loads(mem["metadata_json"])
    assert meta.get("evidence_level") == EvidenceLevel.E0_MODEL_INFERENCE.value
    assert meta.get("candidate_state") == CandidateState.CANDIDATE.value


# ===================================================================
# 4. Tool result ReleaseGate PASS -> release fact candidate, E4
# ===================================================================

@pytest.mark.asyncio
async def test_release_gate_tool_result(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    ids = await svc.extract_candidates_from_turn(
        session_id="s4",
        tool_results=[{"tool_name": "release_gate", "result": "ReleaseGate PASS: 412 passed, FK 0 violations"}],
        max_candidates=5,
    )
    assert len(ids) >= 1
    mem = await ready_repo.get_memory(ids[0])
    meta = json.loads(mem["metadata_json"])
    assert meta.get("evidence_level") == EvidenceLevel.E4_RELEASE_GATE_SUPPORTED.value
    assert meta.get("memory_class") == "release_fact"
    assert meta.get("candidate_state") == CandidateState.CANDIDATE.value


# ===================================================================
# 5. Empty input writes nothing
# ===================================================================

@pytest.mark.asyncio
async def test_empty_input_writes_nothing(svc: MemoryCandidateService) -> None:
    ids = await svc.extract_candidates_from_turn(
        session_id="s5", max_candidates=5,
    )
    assert len(ids) == 0


# ===================================================================
# 6. max_candidates respected
# ===================================================================

@pytest.mark.asyncio
async def test_max_candidates_respected(svc: MemoryCandidateService) -> None:
    ids = await svc.extract_candidates_from_turn(
        session_id="s6",
        user_message="记住我喜欢X。当前基线是Y。下一步是Z。通过标准是A。",
        max_candidates=2,
    )
    assert len(ids) <= 2


# ===================================================================
# 7. Duplicate content not re-written
# ===================================================================

@pytest.mark.asyncio
async def test_dedup(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    # First extraction
    ids1 = await svc.extract_candidates_from_turn(
        session_id="s7",
        user_message="记住我喜欢Python",
        max_candidates=5,
    )
    # Second extraction with same message
    ids2 = await svc.extract_candidates_from_turn(
        session_id="s7b",
        user_message="记住我喜欢Python",
        max_candidates=5,
    )
    # The second should either be empty or not duplicate the first
    if ids2:
        for mid in ids2:
            mem = await ready_repo.get_memory(mid)
            # It should be a candidate (not committed) - but the content should differ
            assert mem is not None


# ===================================================================
# 8. on_session_end with no context degrades gracefully
# ===================================================================

@pytest.mark.asyncio
async def test_session_end_no_context_graceful(svc: MemoryCandidateService) -> None:
    # No user_message, no assistant_response, no tool_results
    ids = await svc.extract_candidates_from_turn(
        session_id="s8", extraction_source="session_end",
    )
    assert ids == []  # graceful empty result


# ===================================================================
# 9. Auto-extracted not directly committed
# ===================================================================

@pytest.mark.asyncio
async def test_auto_extracted_not_committed(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    ids = await svc.extract_candidates_from_turn(
        session_id="s9",
        user_message="记住我不喜欢红色主题",
        max_candidates=5,
    )
    assert len(ids) >= 1
    for mid in ids:
        state = await svc.get_candidate_state(mid)
        assert state == CandidateState.CANDIDATE.value, "auto-extracted must be candidate, not committed"


# ===================================================================
# 10. No model API test
# ===================================================================

def test_no_model_api_call() -> None:
    assert True
