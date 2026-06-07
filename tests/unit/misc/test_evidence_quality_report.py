"""Tests for MemoryX Evidence Quality Report (24.2C)."""
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
    return MemoryRepository(tmp_path / "evidence_quality.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.fixture
def fake_bridge(ready_repo: MemoryRepository):
    class FakeBridge:
        def __init__(self, repo):
            self.repository = repo
            self.query_api = None
        async def on_tool_call(self, **kwargs):
            return {"event": "on_tool_call", "decision": "allow", "should_block": False, "guard_block": "", "metadata": {"degraded": False}}
    return FakeBridge(ready_repo)


@pytest.fixture
async def seeded_evidence_repo(ready_repo: MemoryRepository) -> MemoryRepository:
    """Seed with memories at various evidence levels."""
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())

    # E2 committed (high confidence)
    await svc.create_candidate(MemoryCandidateRequest(
        content="User prefers dark mode.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value,
        confidence=0.95,
    ))

    # E0 candidate (low confidence)
    await svc.create_candidate(MemoryCandidateRequest(
        content="Possible fact from inference.",
        memory_type="FACT",
        source_type="assistant_inference",
        evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
        confidence=0.2,
    ))

    # E3 candidate (medium confidence)
    await svc.create_candidate(MemoryCandidateRequest(
        content="Tool verified fact.",
        memory_type="FACT",
        source_type="tool_result",
        evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED.value,
        confidence=0.85,
    ))

    # E1 candidate (low confidence)
    await svc.create_candidate(MemoryCandidateRequest(
        content="User stated something.",
        memory_type="FACT",
        source_type="user",
        evidence_level=EvidenceLevel.E1_USER_STATED.value,
        confidence=0.15,
    ))

    return ready_repo


# ===================================================================
# 1. count_memories_by_evidence_level groups E0/E1/E2/E3/E4
# ===================================================================

@pytest.mark.asyncio
async def test_count_by_evidence_level(ready_repo, seeded_evidence_repo) -> None:
    counts = await ready_repo.count_memories_by_evidence_level()
    assert isinstance(counts, dict)
    # We seeded E0, E1, E2, E3
    assert counts.get("E0_MODEL_INFERENCE", 0) >= 1
    assert counts.get("E1_USER_STATED", 0) >= 1
    assert counts.get("E2_USER_CONFIRMED", 0) >= 1
    assert counts.get("E3_TOOL_OR_TEST_SUPPORTED", 0) >= 1


# ===================================================================
# 2. Missing evidence_level counts as 'missing'
# ===================================================================

@pytest.mark.asyncio
async def test_missing_evidence_level(ready_repo: MemoryRepository) -> None:
    # Insert a raw memory with no evidence_level in metadata
    record = MemoryRecord(
        id="raw-no-ev",
        content="Raw memory without evidence level.",
        metadata_json='{"candidate_state": "committed"}',
    )
    await ready_repo.store_memory(record)
    counts = await ready_repo.count_memories_by_evidence_level()
    assert counts.get("missing", 0) >= 1


# ===================================================================
# 3. Invalid metadata_json counts as 'unknown'
# ===================================================================

@pytest.mark.asyncio
async def test_invalid_metadata_counts_unknown(ready_repo: MemoryRepository) -> None:
    record = MemoryRecord(
        id="bad-meta",
        content="Memory with broken metadata.",
        metadata_json='NOT VALID JSON{{{',
    )
    await ready_repo.store_memory(record)
    counts = await ready_repo.count_memories_by_evidence_level()
    assert counts.get("unknown", 0) >= 1


# ===================================================================
# 4. low_quality_candidate_count counts E0 candidates
# ===================================================================

@pytest.mark.asyncio
async def test_low_quality_e0_candidate(ready_repo, seeded_evidence_repo) -> None:
    lq = await ready_repo.count_low_quality_candidates()
    assert lq["e0_candidate_count"] >= 1
    assert lq["low_quality_candidate_count"] >= 1


# ===================================================================
# 5. confidence < 0.3 counts as low_quality
# ===================================================================

@pytest.mark.asyncio
async def test_low_quality_low_confidence(ready_repo, seeded_evidence_repo) -> None:
    lq = await ready_repo.count_low_quality_candidates()
    # E1 with confidence 0.15 should count as low quality
    assert lq["low_quality_candidate_count"] >= 2  # E0 + E1 low conf


# ===================================================================
# 6. memory(action=usage) returns evidence_quality
# ===================================================================

@pytest.mark.asyncio
async def test_usage_returns_evidence_quality(fake_bridge, seeded_evidence_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "usage"})
    assert result["ok"] is True
    assert "evidence_quality" in result
    eq = result["evidence_quality"]
    assert "by_evidence_level" in eq
    assert "by_candidate_state" in eq
    assert "low_quality_candidate_count" in eq
    assert "e0_candidate_count" in eq
    assert "missing_evidence_count" in eq
    assert "unknown_metadata_count" in eq


# ===================================================================
# 7. usage does not expose DB path or secrets
# ===================================================================

@pytest.mark.asyncio
async def test_usage_no_secrets(fake_bridge, seeded_evidence_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "usage"})
    text = json.dumps(result)
    assert ".db" not in text
    assert "api_key" not in text.lower()
    assert "secret" not in text.lower() or "not exposed" in text


# ===================================================================
# 8. JSON export includes evidence_quality summary
# ===================================================================

@pytest.mark.asyncio
async def test_json_export_evidence_quality(fake_bridge, seeded_evidence_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "json"})
    assert result["ok"] is True
    assert "evidence_quality" in result
    eq = result["evidence_quality"]
    assert "by_evidence_level" in eq
    assert "low_quality_candidate_count" in eq


# ===================================================================
# 9. Does not use SQLite JSON1
# ===================================================================

@pytest.mark.asyncio
async def test_no_json1_functions(ready_repo: MemoryRepository) -> None:
    """Verify evidence quality methods use Python parsing, not SQLite JSON1."""
    import inspect
    src = inspect.getsource(type(ready_repo).count_memories_by_evidence_level)
    assert "json_extract" not in src
    assert "json_each" not in src
    assert "json(" not in src.lower() or "json.loads" in src

    src2 = inspect.getsource(type(ready_repo).count_low_quality_candidates)
    assert "json_extract" not in src2
    assert "json_each" not in src2


# ===================================================================
# 10. FK check still 0
# ===================================================================

@pytest.mark.asyncio
async def test_fk_check_zero(ready_repo: MemoryRepository) -> None:
    row = await ready_repo.db.fetchone("PRAGMA foreign_key_check;", ())
    # FK check returns rows only if violations exist; empty = pass
    rows = await ready_repo.db.fetchall("PRAGMA foreign_key_check;", ())
    assert len(rows) == 0, f"FK violations: {rows}"
