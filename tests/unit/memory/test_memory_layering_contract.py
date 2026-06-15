"""Tests for MemoryX memory layering (24.3B)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.hermes_provider import MemoryXHermesProvider
from memoryx.services.memory_candidate_service import (
    EvidenceLevel,
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)
from memoryx.storage import MemoryRecord, MemoryRepository


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "memory_layering.db")


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


# ===================================================================
# resolve_memory_layer
# ===================================================================

def test_resolve_layer_policy() -> None:
    # Policy layer via memory_class (not memory_type)
    assert MemoryCandidatePolicy.resolve_memory_layer("FACT", "global", metadata={"memory_class": "policy"}) == "policy"
    assert MemoryCandidatePolicy.resolve_memory_layer("FACT", "global", metadata={"memory_class": "guard"}) == "guard"
    # Fallback: memory_type in (POLICY, RULE, GUARD) still works for backward compat
    assert MemoryCandidatePolicy.resolve_memory_layer("POLICY", "global") == "policy"
    assert MemoryCandidatePolicy.resolve_memory_layer("RULE", "global") == "policy"
    assert MemoryCandidatePolicy.resolve_memory_layer("GUARD", "global") == "guard"


def test_resolve_layer_project() -> None:
    assert MemoryCandidatePolicy.resolve_memory_layer("PROJECT", "project") == "project"
    assert MemoryCandidatePolicy.resolve_memory_layer("TASK", "global") == "project"
    # scope=project
    assert MemoryCandidatePolicy.resolve_memory_layer("FACT", "project") == "project"


def test_resolve_layer_session() -> None:
    assert MemoryCandidatePolicy.resolve_memory_layer("FACT", "session") == "session"
    # session_id present, scope not explicit
    assert MemoryCandidatePolicy.resolve_memory_layer("FACT", "", session_id="sess-1") == "session"
    assert MemoryCandidatePolicy.resolve_memory_layer("FACT", "custom", session_id="sess-1") == "session"


def test_resolve_layer_long_term() -> None:
    assert MemoryCandidatePolicy.resolve_memory_layer("PREFERENCE", "user") == "long_term"
    assert MemoryCandidatePolicy.resolve_memory_layer("FACT", "global") == "long_term"
    assert MemoryCandidatePolicy.resolve_memory_layer("LESSON", "global") == "long_term"
    assert MemoryCandidatePolicy.resolve_memory_layer("FACT", "user") == "long_term"


def test_resolve_layer_explicit_override() -> None:
    # Explicit memory_layer in metadata takes priority
    result = MemoryCandidatePolicy.resolve_memory_layer("FACT", "global", metadata={"memory_layer": "policy"})
    assert result == "policy"
    result = MemoryCandidatePolicy.resolve_memory_layer("POLICY", "global", metadata={"memory_layer": "long_term"})
    assert result == "long_term"


# ===================================================================
# create_candidate writes memory_layer
# ===================================================================

@pytest.mark.asyncio
async def test_create_candidate_writes_layer(ready_repo: MemoryRepository) -> None:
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    # Policy via FACT + memory_class (not memory_type=POLICY)
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content="Policy test", memory_type="FACT", scope="global",
        source_type="user", metadata={"memory_class": "policy"},
    ))
    meta = await svc.get_candidate_state(mid)
    assert meta is not None

    # Read from DB to check metadata
    row = await ready_repo.get_memory(mid)
    assert row is not None
    md = json.loads(row.get("metadata_json", "{}"))
    assert "memory_layer" in md
    assert md["memory_layer"] == "policy"
    assert md["layer_source"] == "auto"


@pytest.mark.asyncio
async def test_create_candidate_writes_layer_project(ready_repo: MemoryRepository) -> None:
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    mid = await svc.create_candidate(MemoryCandidateRequest(content="Project task", memory_type="PROJECT", scope="project", source_type="user"))
    row = await ready_repo.get_memory(mid)
    md = json.loads(row.get("metadata_json", "{}"))
    assert md["memory_layer"] == "project"


@pytest.mark.asyncio
async def test_create_candidate_writes_layer_long_term(ready_repo: MemoryRepository) -> None:
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    mid = await svc.create_candidate(MemoryCandidateRequest(content="A fact", memory_type="FACT", scope="global", source_type="user"))
    row = await ready_repo.get_memory(mid)
    md = json.loads(row.get("metadata_json", "{}"))
    assert md["memory_layer"] == "long_term"


# ===================================================================
# verify/commit does not delete memory_layer
# ===================================================================

@pytest.mark.asyncio
async def test_verify_preserves_layer(ready_repo: MemoryRepository) -> None:
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    mid = await svc.create_candidate(MemoryCandidateRequest(content="Verify layer test", memory_type="FACT", scope="global", source_type="user"))

    # Verify (must pass evidence_ids)
    ok = await svc.verify_candidate(mid, evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, evidence_ids=["ev-1"])
    assert ok is True

    row = await ready_repo.get_memory(mid)
    md = json.loads(row.get("metadata_json", "{}"))
    assert "memory_layer" in md
    assert md["memory_layer"] == "long_term"


# ===================================================================
# provider add target maps to correct layer
# ===================================================================

@pytest.mark.asyncio
async def test_provider_add_policy_layer(fake_bridge, ready_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "add", "target": "policy", "content": "Always check FK constraints."})
    assert result["ok"] is True
    mid = result["memory_id"]
    row = await ready_repo.get_memory(mid)
    md = json.loads(row.get("metadata_json", "{}"))
    assert md["memory_layer"] in ("policy",)


@pytest.mark.asyncio
async def test_provider_add_project_layer(fake_bridge, ready_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "add", "target": "project", "content": "Release gate setup."})
    assert result["ok"] is True
    mid = result["memory_id"]
    row = await ready_repo.get_memory(mid)
    md = json.loads(row.get("metadata_json", "{}"))
    assert md["memory_layer"] == "project"


# ===================================================================
# usage returns by_memory_layer
# ===================================================================

@pytest.mark.asyncio
async def test_usage_returns_layer_quality(fake_bridge, ready_repo) -> None:
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    # Policy via memory_class, not memory_type
    await svc.create_candidate(MemoryCandidateRequest(content="Policy rule", memory_type="FACT", scope="global", source_type="user", metadata={"memory_class": "policy"}))
    await svc.create_candidate(MemoryCandidateRequest(content="Project plan", memory_type="PROJECT", scope="project", source_type="user"))
    await svc.create_candidate(MemoryCandidateRequest(content="Fact note", memory_type="FACT", scope="global", source_type="user"))

    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "usage"})
    assert result["ok"] is True
    assert "layer_quality" in result
    lq = result["layer_quality"]
    assert "by_memory_layer" in lq


# ===================================================================
# export annotates layer
# ===================================================================

@pytest.mark.asyncio
async def test_export_annotates_layer(fake_bridge, ready_repo) -> None:
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    await svc.create_candidate(MemoryCandidateRequest(content="Some fact.", memory_type="FACT", scope="global", source_type="user"))

    provider = MemoryXHermesProvider(bridge=fake_bridge)
    # Use include_candidates=True since the memory is a candidate
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "markdown", "include_candidates": True})
    assert result["ok"] is True
    text = result.get("text", "")
    assert "layer=" in text


# ===================================================================
# no JSON1 dependency
# ===================================================================

@pytest.mark.asyncio
async def test_no_json1_in_layer_methods(ready_repo: MemoryRepository) -> None:
    import inspect
    src = inspect.getsource(type(ready_repo).count_memories_by_layer)
    assert "json_extract" not in src
    assert "json_each" not in src


# ===================================================================
# missing layer -> missing count
# ===================================================================

@pytest.mark.asyncio
async def test_missing_layer_count(ready_repo: MemoryRepository) -> None:
    record = MemoryRecord(
        id="no-layer",
        content="Legacy memory without layer.",
        metadata_json='{"candidate_state": "committed"}',
    )
    await ready_repo.store_memory(record)
    lq = await ready_repo.layer_quality_summary()
    assert lq["missing_layer_count"] >= 1


# ===================================================================
# illegal metadata -> unknown layer
# ===================================================================

@pytest.mark.asyncio
async def test_unknown_layer_from_bad_metadata(ready_repo: MemoryRepository) -> None:
    record = MemoryRecord(
        id="bad-layer-meta",
        content="Broken metadata.",
        metadata_json='NOT JSON{{{',
    )
    await ready_repo.store_memory(record)
    lq = await ready_repo.layer_quality_summary()
    assert lq["unknown_layer_count"] >= 1