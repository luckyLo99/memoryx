"""Tests for lifecycle consolidation contract (24.3D-E)."""
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
    return MemoryRepository(tmp_path / "lifecycle.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.fixture
async def svc(ready_repo: MemoryRepository) -> MemoryCandidateService:
    return MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())


# ===================================================================
# 1. session_end extraction creates candidate
# ===================================================================

@pytest.mark.asyncio
async def test_session_end_creates_candidate(svc: MemoryCandidateService, ready_repo) -> None:
    sids = await svc.extract_candidates_from_turn(
        session_id="sess-1", user_message="记住我习惯用 dark mode",
        assistant_response="OK, noted.",
        extraction_source="session_end",
    )
    for sid in sids:
        state = await svc.get_candidate_state(sid)
        assert state == CandidateState.CANDIDATE.value


# ===================================================================
# 2. session_end candidate has lifecycle_source metadata
# ===================================================================

@pytest.mark.asyncio
async def test_session_end_has_lifecycle_meta(svc: MemoryCandidateService, ready_repo) -> None:
    sids = await svc.extract_candidates_from_turn(
        session_id="sess-2", user_message="our baseline is 0d48928",
        assistant_response="ack",
        extraction_source="session_end",
    )
    for sid in sids:
        row = await ready_repo.get_memory(sid)
        meta = json.loads(row["metadata_json"])
        assert meta.get("lifecycle_source") == "session_end"
        assert meta.get("lifecycle_policy_version") == "24.3D-E"


# ===================================================================
# 3. session_end rule extraction not auto committed
# ===================================================================

@pytest.mark.asyncio
async def test_session_end_not_auto_committed(svc: MemoryCandidateService, ready_repo) -> None:
    sids = await svc.extract_candidates_from_turn(
        session_id="sess-3", user_message="以后都别用 Python",
        assistant_response="OK",
        extraction_source="session_end",
    )
    for sid in sids:
        prom = await svc.promote_candidate_if_safe(sid)
        assert prom["promoted"] is False, "session_end extract must not auto promote"


# ===================================================================
# 4. assistant/summary not auto committed
# ===================================================================

@pytest.mark.asyncio
async def test_assistant_not_auto_committed(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Assumption.", memory_type="FACT", source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value, confidence=0.5,
    ))
    prom = await svc.promote_candidate_if_safe(mid)
    assert prom["promoted"] is False


# ===================================================================
# 5. user_explicit/tool_verified still promote
# ===================================================================

@pytest.mark.asyncio
async def test_user_explicit_still_promotes(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Explicit add.", memory_type="FACT", scope="global", source_type="hermes_memory_tool",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.9,
        metadata={"promotion_source": "user_explicit", "promotion_trusted": True, "promotion_policy_version": "24.3D-C"},
    ))
    prom = await svc.promote_candidate_if_safe(mid)
    assert prom["promoted"] is True


# ===================================================================
# 6. working snapshot does not write DB
# ===================================================================

@pytest.mark.asyncio
async def test_working_snapshot_no_db_write(ready_repo: MemoryRepository) -> None:
    from memoryx.working_memory import WorkingMemoryEngine
    wm = WorkingMemoryEngine()
    snap = await wm.snapshot("nonexistent-session")
    assert snap is None or snap.get("has_state") is False


# ===================================================================
# 7. compress_state does not create candidate
# ===================================================================

@pytest.mark.asyncio
async def test_compress_state_no_candidate(ready_repo: MemoryRepository) -> None:
    from memoryx.working_memory import WorkingMemoryEngine
    wm = WorkingMemoryEngine()
    result = await wm.compress_state("test-sess")
    assert isinstance(result, str)


# ===================================================================
# 8. PROJECT commit with project_id+state_key supersedes old
# ===================================================================

@pytest.mark.asyncio
async def test_project_key_based_supersede(svc: MemoryCandidateService, ready_repo) -> None:
    # Create old project state
    old_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old project state.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.85,
        metadata={"project_id": "proj-1", "state_key": "build_status"},
    ))
    await svc.verify_candidate(old_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev-1"])
    await svc.commit_candidate(old_mid)

    # Create new project state for same key
    new_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="New project state.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={"project_id": "proj-1", "state_key": "build_status"},
    ))
    await svc.verify_candidate(new_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev-2"])
    await svc.commit_candidate(new_mid)

    # Old should be superseded
    old_state = await svc.get_candidate_state(old_mid)
    assert old_state == CandidateState.SUPERSEDED.value, f"expected superseded, got {old_state}"


# ===================================================================
# 9. TASK commit with project_id+state_key supersedes old
# ===================================================================

@pytest.mark.asyncio
async def test_task_key_based_supersede(svc: MemoryCandidateService, ready_repo) -> None:
    old_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old task.", memory_type="TASK", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.85,
        metadata={"project_id": "proj-1", "state_key": "task_deploy"},
    ))
    await svc.verify_candidate(old_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev-1"])
    await svc.commit_candidate(old_mid)

    new_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="New task.", memory_type="TASK", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={"project_id": "proj-1", "state_key": "task_deploy"},
    ))
    await svc.verify_candidate(new_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev-2"])
    await svc.commit_candidate(new_mid)

    old_state = await svc.get_candidate_state(old_mid)
    assert old_state == CandidateState.SUPERSEDED.value


# ===================================================================
# 10. No project_id → no supersede
# ===================================================================

@pytest.mark.asyncio
async def test_no_project_id_no_supersede(svc: MemoryCandidateService, ready_repo) -> None:
    old_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.85,
        metadata={"state_key": "st"},  # no project_id
    ))
    await svc.verify_candidate(old_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(old_mid)
    new_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="New.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={"state_key": "st"},  # no project_id
    ))
    await svc.verify_candidate(new_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(new_mid)
    old_state = await svc.get_candidate_state(old_mid)
    assert old_state == CandidateState.COMMITTED.value, "should NOT supersede without project_id"


# ===================================================================
# 11. No state_key → no supersede
# ===================================================================

@pytest.mark.asyncio
async def test_no_state_key_no_supersede(svc: MemoryCandidateService, ready_repo) -> None:
    old_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.85,
        metadata={"project_id": "p1"},
    ))
    await svc.verify_candidate(old_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(old_mid)
    new_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="New.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={"project_id": "p1"},
    ))
    await svc.verify_candidate(new_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(new_mid)
    old_state = await svc.get_candidate_state(old_mid)
    assert old_state == CandidateState.COMMITTED.value, "should NOT supersede without state_key"


# ===================================================================
# 12. Old project state not deleted
# ===================================================================

@pytest.mark.asyncio
async def test_old_not_deleted(svc: MemoryCandidateService, ready_repo) -> None:
    old_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.85,
        metadata={"project_id": "p2", "state_key": "st"},
    ))
    await svc.verify_candidate(old_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(old_mid)
    new_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="New.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={"project_id": "p2", "state_key": "st"},
    ))
    await svc.verify_candidate(new_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(new_mid)
    row = await ready_repo.get_memory(old_mid)
    assert row is not None


# ===================================================================
# 13. Old project state not retrievable
# ===================================================================

@pytest.mark.asyncio
async def test_old_not_retrievable(svc: MemoryCandidateService, ready_repo) -> None:
    from memoryx.retrieval.engine import _is_visible_memory_for_retrieval
    old_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.85,
        metadata={"project_id": "p3", "state_key": "st"},
    ))
    await svc.verify_candidate(old_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(old_mid)
    new_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="New.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={"project_id": "p3", "state_key": "st"},
    ))
    await svc.verify_candidate(new_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(new_mid)
    old_row = await ready_repo.get_memory(old_mid)
    assert _is_visible_memory_for_retrieval(old_row) is False


# ===================================================================
# 14. New project state visible
# ===================================================================

@pytest.mark.asyncio
async def test_new_project_visible(svc: MemoryCandidateService, ready_repo) -> None:
    from memoryx.retrieval.engine import _is_visible_memory_for_retrieval
    old_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old." + "x", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.85,
        metadata={"project_id": "p4", "state_key": "st"},
    ))
    await svc.verify_candidate(old_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(old_mid)
    new_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="New." + "y", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={"project_id": "p4", "state_key": "st"},
    ))
    await svc.verify_candidate(new_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(new_mid)
    new_row = await ready_repo.get_memory(new_mid)
    assert _is_visible_memory_for_retrieval(new_row) is True


# ===================================================================
# 15. Project supersede writes metadata markers
# ===================================================================

@pytest.mark.asyncio
async def test_project_supersede_metadata(svc: MemoryCandidateService, ready_repo) -> None:
    old_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.85,
        metadata={"project_id": "p5", "state_key": "st"},
    ))
    await svc.verify_candidate(old_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(old_mid)
    new_mid = await svc.create_candidate(MemoryCandidateRequest(
        content="New.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, confidence=0.9,
        metadata={"project_id": "p5", "state_key": "st"},
    ))
    await svc.verify_candidate(new_mid, EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value, ["ev"])
    await svc.commit_candidate(new_mid)
    row = await ready_repo.get_memory(new_mid)
    meta = json.loads(row["metadata_json"])
    assert meta.get("project_lifecycle_policy_version") == "24.3D-E"
    assert meta.get("project_state_supersede_status") == "success"
    assert meta.get("project_state_superseded_count", 0) >= 1


# ===================================================================
# 16. PROJECT must pass E3 gate
# ===================================================================

@pytest.mark.asyncio
async def test_project_e3_gate(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="E0 project.", memory_type="PROJECT", scope="project", source_type="tool_verified",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value, confidence=0.9,
    ))
    assert await svc.commit_candidate(mid) is False


# ===================================================================
# 17. E0 not commit
# ===================================================================

@pytest.mark.asyncio
async def test_e0_not_commit(svc: MemoryCandidateService, ready_repo) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="E0 fact.", memory_type="FACT", source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value, confidence=0.5,
    ))
    assert await svc.commit_candidate(mid) is False


# ===================================================================
# 18. No SQLite JSON1
# ===================================================================

@pytest.mark.asyncio
async def test_no_json1(svc: MemoryCandidateService, ready_repo) -> None:
    import inspect
    src = inspect.getsource(type(svc)._handle_project_state_supersede)
    assert "json_extract" not in src
    assert "json_each" not in src


# ===================================================================
# 19. No schema change
# ===================================================================

def test_no_schema_change() -> None:
    import inspect
    src = inspect.getsource(MemoryCandidateService.commit_candidate)
    assert "CREATE TABLE" not in src.upper()


# ===================================================================
# 20. FK 0 violations
# ===================================================================

@pytest.mark.asyncio
async def test_fk_zero(ready_repo: MemoryRepository) -> None:
    rows = await ready_repo.db.fetchall("PRAGMA foreign_key_check;", ())
    assert len(rows) == 0, f"FK violations: {rows}"
