"""Repository contract tests for MemoryX 24.1B Candidate Memory Pipeline.

Coverage:
  1. update_memory_metadata merges patch, doesn't overwrite unknown fields
  2. Invalid metadata_json repaired with warning
  3. update_memory_active_state rejects illegal active_state
  4. get_memory reads by memory_id/id
  5. All candidate metadata persisted and re-readable
  6. foreign_key_check = 0
  7. store_memory legacy call still compatible
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.storage import MemoryRecord, MemoryRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "candidate_contract.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


# ---------------------------------------------------------------------------
# update_memory_metadata merges patch, preserves unknown fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_metadata_merges_patch(ready_repo: MemoryRepository) -> None:
    """update_memory_metadata should merge patch into existing metadata."""
    initial_meta = json.dumps({"existing_key": "existing_value", "other": 42})
    mid = await ready_repo.store_memory(
        MemoryRecord(memory_type="FACT", content="Metadata merge test", metadata_json=initial_meta)
    )

    ok = await ready_repo.update_memory_metadata(mid, {"new_key": "new_value"})
    assert ok, "update should succeed"

    mem = await ready_repo.get_memory(mid)
    assert mem is not None
    meta = json.loads(mem["metadata_json"])
    # Existing fields preserved
    assert meta["existing_key"] == "existing_value"
    assert meta["other"] == 42
    # New field added
    assert meta["new_key"] == "new_value"


# ---------------------------------------------------------------------------
# Invalid metadata_json repaired with warning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_metadata_repairs_invalid_json(ready_repo: MemoryRepository) -> None:
    """Invalid metadata_json should be repaired with a warning field."""
    bad_meta = "{invalid json here}"
    mid = await ready_repo.store_memory(
        MemoryRecord(memory_type="FACT", content="Bad metadata test", metadata_json=bad_meta)
    )

    ok = await ready_repo.update_memory_metadata(mid, {"fixed": True})
    assert ok

    mem = await ready_repo.get_memory(mid)
    meta = json.loads(mem["metadata_json"])
    assert meta["fixed"] is True
    # Repair warning should be present
    assert "_metadata_repair_warning" in meta


# ---------------------------------------------------------------------------
# update_memory_active_state rejects illegal values
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_active_state_rejects_illegal(ready_repo: MemoryRepository) -> None:
    """update_memory_active_state should reject illegal active_state values."""
    mid = await ready_repo.store_memory(
        MemoryRecord(memory_type="FACT", content="Active state test")
    )

    ok = await ready_repo.update_memory_active_state(mid, "illegal_state")
    assert not ok, "illegal state should be rejected"

    ok = await ready_repo.update_memory_active_state(mid, "super_duper")
    assert not ok, "illegal state should be rejected"

    # Legal states still work
    ok = await ready_repo.update_memory_active_state(mid, "archived")
    assert ok

    mem = await ready_repo.get_memory(mid)
    assert mem["active_state"] == "archived"


# ---------------------------------------------------------------------------
# update_memory_active_state for non-existent memory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_active_state_nonexistent(ready_repo: MemoryRepository) -> None:
    """update_memory_active_state should return False for non-existent memory."""
    ok = await ready_repo.update_memory_active_state("nonexistent", "archived")
    assert not ok


# ---------------------------------------------------------------------------
# update_memory_metadata for non-existent memory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_metadata_nonexistent(ready_repo: MemoryRepository) -> None:
    """update_memory_metadata should return False for non-existent memory."""
    ok = await ready_repo.update_memory_metadata("nonexistent", {"key": "val"})
    assert not ok


# ---------------------------------------------------------------------------
# get_memory reads by ID
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_memory_by_id(ready_repo: MemoryRepository) -> None:
    """get_memory should return a dict with both id and memory_id."""
    mid = await ready_repo.store_memory(
        MemoryRecord(memory_type="FACT", content="Get memory test")
    )
    mem = await ready_repo.get_memory(mid)
    assert mem is not None
    assert mem["id"] == mid
    assert "memory_id" in mem, "memory_id alias should exist"
    assert mem["memory_id"] == mid


# ---------------------------------------------------------------------------
# Candidate metadata persisted and re-readable (via raw DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_candidate_metadata_persisted(ready_repo: MemoryRepository) -> None:
    """All candidate metadata fields should be written and readable."""
    candidate_meta = {
        "candidate_state": "candidate",
        "evidence_level": "E0_MODEL_INFERENCE",
        "source_type": "assistant_inference",
        "source_event_id": "evt-abc",
        "evidence_ids": ["evt-1", "evt-2"],
        "confidence": 0.5,
        "verified_at": None,
        "committed_at": None,
        "rejection_reason": None,
        "superseded_by": None,
        "superseded_at": None,
    }
    mid = await ready_repo.store_memory(
        MemoryRecord(
            memory_type="FACT",
            content="Candidate metadata persistence test",
            metadata_json=json.dumps(candidate_meta),
        )
    )

    mem = await ready_repo.get_memory(mid)
    meta = json.loads(mem["metadata_json"])
    for key, expected in candidate_meta.items():
        assert key in meta, f"key {key} missing from persisted metadata"
        assert meta[key] == expected, f"key {key}: expected {expected}, got {meta[key]}"


# ---------------------------------------------------------------------------
# foreign_key_check = 0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_foreign_key_check_still_zero(ready_repo: MemoryRepository) -> None:
    """Add a record and verify FK check returns 0."""
    await ready_repo.store_memory(
        MemoryRecord(memory_type="FACT", content="FK check test")
    )
    row = await ready_repo.db.fetchone("PRAGMA foreign_key_check;")
    # Should be empty/None (no FK violations)
    assert row is None or len(row) == 0


# ---------------------------------------------------------------------------
# store_memory legacy call still compatible
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_store_memory_compatible(ready_repo: MemoryRepository) -> None:
    """store_memory with minimal fields should still work."""
    mid = await ready_repo.store_memory(
        MemoryRecord(memory_type="FACT", content="Legacy compat test")
    )
    assert mid is not None
    mem = await ready_repo.get_memory(mid)
    assert mem is not None
    assert mem["content"] == "Legacy compat test"
    assert mem["memory_type"] == "FACT"
    # Legacy backwards compat: memory_id alias
    assert mem.get("memory_id") == mid


# ---------------------------------------------------------------------------
# update_memory_metadata with empty existing metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_metadata_empty_existing(ready_repo: MemoryRepository) -> None:
    """update_memory_metadata on memory with empty metadata should work."""
    mid = await ready_repo.store_memory(
        MemoryRecord(memory_type="FACT", content="Empty meta test", metadata_json="{}")
    )
    ok = await ready_repo.update_memory_metadata(mid, {"test_key": "test_val"})
    assert ok

    mem = await ready_repo.get_memory(mid)
    meta = json.loads(mem["metadata_json"])
    assert meta["test_key"] == "test_val"


# ---------------------------------------------------------------------------
# update_memory_metadata does not
#  overwrite content/memory_type/scope
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_metadata_does_not_overwrite_content(ready_repo: MemoryRepository) -> None:
    """update_memory_metadata should only touch metadata_json and updated_at."""
    mid = await ready_repo.store_memory(
        MemoryRecord(memory_type="FACT", content="Original content", scope="global")
    )
    await ready_repo.update_memory_metadata(mid, {"new_meta": True})

    mem = await ready_repo.get_memory(mid)
    assert mem["content"] == "Original content"
    assert mem["memory_type"] == "FACT"
    assert mem["scope"] == "global"
