"""Tests for candidate hygiene: retrieval filtering + stale/cleanup."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.retrieval.engine import _is_visible_memory_for_retrieval
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
    return MemoryRepository(tmp_path / "hygiene.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.fixture
def svc(ready_repo: MemoryRepository) -> MemoryCandidateService:
    return MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())


# ===================================================================
# 1. E0 candidate not visible by default
# ===================================================================

def test_e0_candidate_not_visible_by_default() -> None:
    rec = {"metadata_json": json.dumps({"candidate_state": "candidate"})}
    assert _is_visible_memory_for_retrieval(rec) is False


# ===================================================================
# 2. committed visible
# ===================================================================

def test_committed_visible() -> None:
    rec = {"metadata_json": json.dumps({"candidate_state": "committed"})}
    assert _is_visible_memory_for_retrieval(rec) is True


# ===================================================================
# 3. verified visible
# ===================================================================

def test_verified_visible() -> None:
    rec = {"metadata_json": json.dumps({"candidate_state": "verified"})}
    assert _is_visible_memory_for_retrieval(rec) is True


# ===================================================================
# 4. candidate visible with include_candidates=True
# ===================================================================

def test_candidate_visible_with_include_candidates() -> None:
    rec = {"metadata_json": json.dumps({"candidate_state": "candidate"})}
    assert _is_visible_memory_for_retrieval(rec, include_candidates=True) is True


# ===================================================================
# 5. rejected/superseded/stale never visible
# ===================================================================

def test_rejected_never_visible() -> None:
    rec = {"metadata_json": json.dumps({"candidate_state": "rejected"})}
    assert _is_visible_memory_for_retrieval(rec) is False
    assert _is_visible_memory_for_retrieval(rec, include_candidates=True) is False


def test_superseded_never_visible() -> None:
    rec = {"metadata_json": json.dumps({"candidate_state": "superseded"})}
    assert _is_visible_memory_for_retrieval(rec) is False


def test_stale_never_visible() -> None:
    rec = {"metadata_json": json.dumps({"candidate_state": "stale"})}
    assert _is_visible_memory_for_retrieval(rec) is False


# ===================================================================
# 6. legacy memory (no candidate_state) still visible
# ===================================================================

def test_legacy_no_candidate_state_visible() -> None:
    rec = {"metadata_json": "{}"}
    assert _is_visible_memory_for_retrieval(rec) is True


# ===================================================================
# 7. invalid metadata_json doesn't crash
# ===================================================================

def test_invalid_metadata_conservative_visible() -> None:
    rec = {"metadata_json": "{invalid json"}
    assert _is_visible_memory_for_retrieval(rec) is True


# ===================================================================
# 8. mark_stale_candidates dry_run doesn't write
# ===================================================================

@pytest.mark.asyncio
async def test_mark_stale_dry_run_no_write(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    await svc.create_candidate(MemoryCandidateRequest(
        content="Will become stale.",
        memory_type="FACT",
        source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
        confidence=0.2,
    ))
    result = await svc.mark_stale_candidates(max_age_days=0, dry_run=True)
    assert result["dry_run"] is True
    # Memory still candidate, not stale
    mems = await ready_repo.list_memories_filtered(limit=10, include_states={"active"})
    assert len(mems) >= 1


# ===================================================================
# 9. mark_stale_candidates marks old candidates stale
# ===================================================================

@pytest.mark.asyncio
async def test_mark_stale_candidates_marks(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old candidate.",
        memory_type="FACT",
        source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
        confidence=0.2,
    ))
    # max_age_days=0 means everything is stale
    result = await svc.mark_stale_candidates(max_age_days=0, dry_run=False)
    assert result["count"] >= 1

    state = await svc.get_candidate_state(mid)
    assert state == "stale"


# ===================================================================
# 10. reject_stale_candidates doesn't physically delete
# ===================================================================

@pytest.mark.asyncio
async def test_reject_stale_no_physical_delete(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Old candidate to reject.",
        memory_type="FACT",
        source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
        confidence=0.2,
    ))
    result = await svc.reject_stale_candidates(max_age_days=0, dry_run=False)
    assert result["count"] >= 1

    # Memory row still exists
    mem = await ready_repo.get_memory(mid)
    assert mem is not None
    assert mem["content"] == "Old candidate to reject."


# ===================================================================
# 11. limit works
# ===================================================================

@pytest.mark.asyncio
async def test_mark_stale_limit(svc: MemoryCandidateService, ready_repo: MemoryRepository) -> None:
    for i in range(5):
        await svc.create_candidate(MemoryCandidateRequest(
            content=f"Candidate {i}.",
            memory_type="FACT",
            source_type="assistant_inference",
            evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
            confidence=0.2,
        ))
    result = await svc.mark_stale_candidates(max_age_days=0, limit=2, dry_run=False)
    assert result["count"] <= 2


# ===================================================================
# 12. FK check still passes
# ===================================================================

@pytest.mark.asyncio
async def test_fk_check_zero(ready_repo: MemoryRepository) -> None:
    row = await ready_repo.db.fetchone("PRAGMA foreign_key_check;")
    assert row is None or len(row) == 0
