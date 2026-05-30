"""Contract tests for MemoryX native memory parity provider + ToolGuard integration."""
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "native_parity_contract.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.fixture
def fake_bridge(ready_repo: MemoryRepository):
    """Bridge where guard allows all tools."""
    class FakeBridge:
        def __init__(self, repo):
            self.repository = repo
            self.query_api = None
        async def on_tool_call(self, **kwargs):
            return {"event": "on_tool_call", "decision": "allow", "should_block": False, "guard_block": "", "metadata": {"degraded": False}}
    return FakeBridge(ready_repo)


# ===================================================================
# 1-10: Basic provider contract tests (from 24.1C)
# ===================================================================

def test_memory_tool_schema_exposed(fake_bridge) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    schemas = provider.get_tool_schemas()
    assert len(schemas) >= 1
    assert schemas[0]["name"] == "memory"


@pytest.mark.asyncio
async def test_memory_tool_routed_to_provider(fake_bridge) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "add", "target": "memory", "content": "Route test."})
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_memory_add_through_candidate_pipeline(fake_bridge, ready_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "add", "target": "memory", "content": "Pipeline test.", "confidence": 0.5})
    mid = result["memory_id"]
    mem = await ready_repo.get_memory(mid)
    assert mem is not None
    meta = json.loads(mem["metadata_json"])
    assert meta.get("candidate_state") is not None
    cs = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    ok = await cs.verify_candidate(mid, evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, evidence_ids=["test"])
    assert ok
    ok = await cs.commit_candidate(mid)
    assert ok, "commit should succeed after verify"


@pytest.mark.asyncio
async def test_replace_does_not_modify_original(fake_bridge, ready_repo) -> None:
    cs = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    orig_id = await cs.create_candidate(MemoryCandidateRequest(content="Original content.", memory_type="FACT", source_type="user", evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.95))
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "replace", "memory_id": orig_id, "content": "Replacement content.", "reason": "Update"})
    assert result["ok"] is True
    assert result["replace_target_id"] == orig_id
    orig = await ready_repo.get_memory(orig_id)
    assert orig["content"] == "Original content."


@pytest.mark.asyncio
async def test_remove_does_not_delete_original(fake_bridge, ready_repo) -> None:
    cs = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    orig_id = await cs.create_candidate(MemoryCandidateRequest(content="Content to be removed.", memory_type="FACT", source_type="user", evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.95))
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "remove", "memory_id": orig_id, "reason": "Stale data"})
    assert result["ok"] is True
    orig = await ready_repo.get_memory(orig_id)
    assert orig is not None
    assert orig["content"] == "Content to be removed."


@pytest.mark.asyncio
async def test_read_usable(fake_bridge, ready_repo) -> None:
    cs = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    mid = await cs.create_candidate(MemoryCandidateRequest(content="Agent test memory.", memory_type="FACT", source_type="user", evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.95))
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "memory_id": mid})
    assert result["ok"] is True
    assert result["memories"][0]["content"] == "Agent test memory."


@pytest.mark.asyncio
async def test_non_memory_tool_unaffected(fake_bridge) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("web_search", {"query": "test"})
    assert result["ok"] is False
    assert "unsupported tool" in result["error"]


@pytest.mark.asyncio
async def test_memoryx_tool_works_independent(fake_bridge) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    schemas = provider.get_tool_schemas()
    assert schemas[0]["name"] == "memory"
    for schema in schemas:
        assert "memory.md" not in schema.get("description", "").lower()


@pytest.mark.asyncio
async def test_add_policy(fake_bridge, ready_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "add", "target": "policy", "content": "Never store raw secrets."})
    assert result["ok"] is True
    mem = await ready_repo.get_memory(result["memory_id"])
    assert mem["memory_type"] == "FACT"
    meta = json.loads(mem["metadata_json"])
    assert meta.get("memory_class") == "policy"


# ===================================================================
# ToolGuard integration tests
# ===================================================================

@pytest.fixture
def bridge_allow(ready_repo):
    class B:
        repository = ready_repo
        query_api = None
        async def on_tool_call(self, **kwargs):
            return {"event": "on_tool_call", "decision": "allow", "should_block": False, "guard_block": "", "metadata": {"degraded": False}}
    return B()


@pytest.fixture
def bridge_block(ready_repo):
    class B:
        repository = ready_repo
        query_api = None
        async def on_tool_call(self, **kwargs):
            return {"event": "on_tool_call", "decision": "block", "should_block": True, "guard_block": "Blocked", "metadata": {"degraded": False}}
    return B()


@pytest.fixture
def bridge_warn(ready_repo):
    class B:
        repository = ready_repo
        query_api = None
        async def on_tool_call(self, **kwargs):
            return {"event": "on_tool_call", "decision": "warn", "should_block": False, "guard_block": "Warning", "metadata": {"degraded": False}}
    return B()


def _guard_should_block(guard):
    """Check if guard result indicates block, supporting both obj and dict."""
    if isinstance(guard, dict):
        return guard.get("should_block", False)
    return getattr(guard, "should_block", False)

def _guard_decision(guard):
    """Get guard decision string."""
    if isinstance(guard, dict):
        return guard.get("decision", "block")
    return getattr(guard, "decision", "block")

async def _dispatch(session_id, tool_name, args, bridge, provider):
    """Simulates plugin.py's on_tool_call guard + provider dispatch."""
    guard = None
    if bridge is not None and hasattr(bridge, "on_tool_call"):
        guard = await bridge.on_tool_call(session_id=session_id, tool_name=tool_name, args=args or {})
    else:
        guard = type("FG", (), {"decision": "allow", "should_block": False, "guard_block": "", "metadata": {"degraded": True}, "to_dict": lambda self: {"event": "on_tool_call", "decision": "allow", "should_block": False, "guard_block": "", "metadata": {"degraded": True}, "session_id": session_id}})()

    if provider is not None and tool_name == "memory":
        if _guard_should_block(guard):
            return {"ok": False, "action": (args or {}).get("action", ""), "error": "blocked by tool guard", "blocked": True, "metadata": {"tool_guard": {"decision": _guard_decision(guard), "should_block": True}}}
        pr = await provider.handle_tool_call(tool_name=tool_name, arguments=args or {}, session_id=session_id)
        if isinstance(pr, dict):
            pm = pr.get("metadata", {})
            gd = _guard_decision(guard)
            gb = guard.get("guard_block", "") if isinstance(guard, dict) else getattr(guard, "guard_block", "")
            gm = guard.get("metadata", {}) if isinstance(guard, dict) else getattr(guard, "metadata", {})
            pm["tool_guard"] = {"decision": gd, "guard_block": (gb or "")[:200], "degraded": gm.get("degraded", False)}
            pr["metadata"] = pm
        return pr

    if hasattr(guard, "to_dict"):
        return guard.to_dict()
    return {"event": "on_tool_call", "decision": getattr(guard, "decision", "allow")}


@pytest.mark.asyncio
async def test_guard_allow_memory_executes(bridge_allow, ready_repo) -> None:
    provider = MemoryXHermesProvider(bridge=bridge_allow)
    result = await _dispatch("s1", "memory", {"action": "add", "target": "memory", "content": "Guard test."}, bridge_allow, provider)
    assert result["ok"] is True
    meta = result.get("metadata", {})
    assert meta["tool_guard"]["decision"] == "allow"
    assert meta["tool_guard"]["degraded"] is False


@pytest.mark.asyncio
async def test_guard_block_prevents_execution(bridge_block, ready_repo) -> None:
    provider = MemoryXHermesProvider(bridge=bridge_block)
    result = await _dispatch("s1", "memory", {"action": "add", "target": "memory", "content": "Blocked."}, bridge_block, provider)
    assert result["ok"] is False
    assert result.get("blocked") is True
    # Verify no memory written
    all_m = await ready_repo.list_memories_filtered(limit=100)
    assert not any("Blocked." in (m.get("content") or "") for m in all_m)


@pytest.mark.asyncio
async def test_guard_warn_allows_with_metadata(bridge_warn, ready_repo) -> None:
    provider = MemoryXHermesProvider(bridge=bridge_warn)
    result = await _dispatch("s1", "memory", {"action": "add", "target": "memory", "content": "Warn test."}, bridge_warn, provider)
    assert result["ok"] is True
    meta = result.get("metadata", {})
    assert meta["tool_guard"]["decision"] == "warn"
    assert meta["tool_guard"]["guard_block"] != ""


@pytest.mark.asyncio
async def test_guard_missing_degraded(bridge_allow, ready_repo) -> None:
    class BridgeNoGuard:
        repository = ready_repo
        query_api = None
    provider = MemoryXHermesProvider(bridge=BridgeNoGuard())
    result = await _dispatch("s1", "memory", {"action": "usage"}, None, provider)
    assert result["ok"] is True
    meta = result.get("metadata", {})
    assert meta["tool_guard"]["degraded"] is True


@pytest.mark.asyncio
async def test_guard_non_memory_unaffected(bridge_allow) -> None:
    result = await _dispatch("s1", "bash", {"command": "ls"}, bridge_allow, None)
    assert result.get("decision") == "allow"


@pytest.mark.asyncio
async def test_add_behavior_unchanged_with_guard(bridge_allow, ready_repo) -> None:
    provider = MemoryXHermesProvider(bridge=bridge_allow)
    result = await _dispatch("s1", "memory", {"action": "add", "target": "memory", "content": "Guard add test."}, bridge_allow, provider)
    assert result["ok"] is True
    assert result["state"] == CandidateState.CANDIDATE.value
    mem = await ready_repo.get_memory(result["memory_id"])
    meta = json.loads(mem["metadata_json"])
    assert meta.get("candidate_state") == CandidateState.CANDIDATE.value
