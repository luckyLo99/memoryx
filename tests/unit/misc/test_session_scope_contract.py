"""Tests for MemoryX session scope hardening (24.3C)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.hermes_provider import MemoryXHermesProvider
from memoryx.retrieval.engine import _is_session_scoped_memory, _session_matches
from memoryx.services.memory_candidate_service import (
    CandidateState,
    EvidenceLevel,
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)
from memoryx.storage import MemoryRecord, MemoryRepository


class FakeVectorStore:
    """Minimal vector store stub for retrieval tests."""
    async def search(self, query_vector, limit=10):
        return []
    async def open(self):
        pass
    async def close(self):
        pass


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "session_scope.db")


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
async def session_seeded(ready_repo: MemoryRepository) -> MemoryRepository:
    """Seed with session-scoped and global memories for two sessions."""
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())

    # Session A scoped memories
    await svc.create_candidate(MemoryCandidateRequest(
        content="Session A memory.", memory_type="FACT", scope="session",
        session_id="sess-A", source_type="user",
    ))
    # Session B scoped memories
    await svc.create_candidate(MemoryCandidateRequest(
        content="Session B memory.", memory_type="FACT", scope="session",
        session_id="sess-B", source_type="user",
    ))
    # Global memory (no session)
    record = MemoryRecord(
        id="global-mem",
        content="Global fact.",
        metadata_json='{"candidate_state": "committed", "memory_layer": "long_term"}',
    )
    await ready_repo.store_memory(record)
    # User preference (no session)
    record2 = MemoryRecord(
        id="pref-mem",
        content="User preference.",
        scope="user",
        metadata_json='{"candidate_state": "committed", "memory_layer": "long_term"}',
    )
    await ready_repo.store_memory(record2)
    # Project memory
    record3 = MemoryRecord(
        id="proj-mem",
        content="Project state.",
        scope="project",
        metadata_json='{"candidate_state": "committed", "memory_layer": "project"}',
    )
    await ready_repo.store_memory(record3)

    return ready_repo


# ===================================================================
# 1. Current session sees own session memory
# ===================================================================

def test_current_session_sees_own() -> None:
    mem_a = {"scope": "session", "session_id": "sess-A", "metadata_json": "{}"}
    assert _is_session_scoped_memory(mem_a) is True
    assert _session_matches(mem_a, "sess-A") is True


# ===================================================================
# 2. Current session does NOT see other session's memory
# ===================================================================

def test_current_session_not_see_foreign() -> None:
    mem_b = {"scope": "session", "session_id": "sess-B", "metadata_json": "{}"}
    assert _is_session_scoped_memory(mem_b) is True
    assert _session_matches(mem_b, "sess-A") is False  # foreign session


# ===================================================================
# 3. Session-scoped without session_id is invisible
# ===================================================================

def test_session_scoped_no_session_id() -> None:
    mem = {"scope": "session", "session_id": None, "metadata_json": "{}"}
    assert _is_session_scoped_memory(mem) is True
    assert _session_matches(mem, "sess-A") is False  # no session_id


# ===================================================================
# 4. include_global=True does not leak foreign session memory
# ===================================================================

@pytest.mark.asyncio
async def test_global_does_not_leak_foreign_session(ready_repo, session_seeded) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(
        query="memory", query_vector=[],
        session_id="sess-A", include_global=True, limit=20,
    )
    texts = " ".join(r.content for r in results)
    assert "Session B memory" not in texts, "foreign session memory leaked"


# ===================================================================
# 5. session_only=True excludes global/user/project
# ===================================================================

@pytest.mark.asyncio
async def test_session_only_excludes_global(ready_repo, session_seeded) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(
        query="memory", query_vector=[],
        session_id="sess-A", session_only=True, limit=20,
    )
    texts = " ".join(r.content for r in results)
    assert "Global fact" not in texts, "global leaked in session_only"


# ===================================================================
# 6. session_only=True keeps only current session memory
# ===================================================================

@pytest.mark.asyncio
async def test_session_only_keeps_current_only(ready_repo, session_seeded) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(
        query="memory", query_vector=[],
        session_id="sess-A", session_only=True, limit=20,
    )
    texts = " ".join(r.content for r in results)
    assert "Session B memory" not in texts, "foreign session leaked in session_only"


# ===================================================================
# 7. Normal mode: global memory is still visible
# ===================================================================

@pytest.mark.asyncio
async def test_normal_mode_global_visible(ready_repo, session_seeded) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(
        query="fact", query_vector=[],
        session_id="sess-A", session_only=False, limit=20,
    )
    texts = " ".join(r.content for r in results)
    assert "Global fact" in texts, "global not visible in normal mode"


# ===================================================================
# 8. memory_layer=session equivalent to scope=session
# ===================================================================

def test_memory_layer_session_equivalent() -> None:
    mem_layer = {"scope": "global", "metadata_json": json.dumps({"memory_layer": "session"})}
    mem_scope = {"scope": "session", "metadata_json": "{}"}
    assert _is_session_scoped_memory(mem_layer) is True
    assert _is_session_scoped_memory(mem_scope) is True


# ===================================================================
# 8b. memory_layer=session + scope=global visible in session_only mode
# ===================================================================

@pytest.mark.asyncio
async def test_session_only_sees_layer_session_global_scope(ready_repo, session_seeded) -> None:
    """session_only=True must return scope=global + memory_layer=session + session_id match."""
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)

    # Seed a memory with scope=global + memory_layer=session + session_id=A
    record = MemoryRecord(
        id="layer-session-global-a",
        content="Session A via layer, global scope.",
        scope="global",
        session_id="sess-A",
        metadata_json=json.dumps({
            "candidate_state": "committed",
            "memory_layer": "session",
        }),
    )
    await ready_repo.store_memory(record)

    results = await engine.retrieve(
        query="via layer", query_vector=[],
        session_id="sess-A", session_only=True, limit=20,
    )
    texts = " ".join(r.content for r in results)
    assert "via layer" in texts, "memory_layer=session should be visible in session_only"


# ===================================================================
# 8c. memory_layer=session + scope=global + foreign session excluded
# ===================================================================

@pytest.mark.asyncio
async def test_session_only_excludes_foreign_layer_session(ready_repo, session_seeded) -> None:
    """session_only=True must exclude scope=global + memory_layer=session + foreign session_id."""
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)

    # Seed a memory with scope=global + memory_layer=session + session_id=B
    record = MemoryRecord(
        id="layer-session-global-b",
        content="Session B via layer, global scope.",
        scope="global",
        session_id="sess-B",
        metadata_json=json.dumps({
            "candidate_state": "committed",
            "memory_layer": "session",
        }),
    )
    await ready_repo.store_memory(record)

    results = await engine.retrieve(
        query="via layer", query_vector=[],
        session_id="sess-A", session_only=True, limit=20,
    )
    texts = " ".join(r.content for r in results)
    assert "Session B via layer" not in texts, "foreign memory_layer=session leaked"


# ===================================================================
# 8d. normal mode: memory_layer=session must match session_id
# ===================================================================

@pytest.mark.asyncio
async def test_normal_mode_layer_session_must_match(ready_repo, session_seeded) -> None:
    """In normal mode, memory_layer=session still requires session_id match."""
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)

    # Seed memory_layer=session with session_id=A
    record = MemoryRecord(
        id="layer-session-match",
        content="Layer session match test.",
        scope="global",
        session_id="sess-A",
        metadata_json=json.dumps({
            "candidate_state": "committed",
            "memory_layer": "session",
        }),
    )
    await ready_repo.store_memory(record)

    # Session B searches - must NOT see session A's memory_layer=session memory
    results = await engine.retrieve(
        query="Layer session match", query_vector=[],
        session_id="sess-B", session_only=False, limit=20,
    )
    texts = " ".join(r.content for r in results)
    assert "Layer session match" not in texts, "foreign memory_layer=session visible in normal mode"


# ===================================================================
# 9. Context assembly doesn't include foreign session memory
# ===================================================================

@pytest.mark.asyncio
async def test_context_assembly_no_foreign_session(ready_repo, session_seeded) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(
        query="memory", query_vector=[], session_id="sess-A", limit=20,
    )
    texts = " ".join(r.content for r in results)
    assert "Session B memory" not in texts


# ===================================================================
# 10. REST query_api supports session_only
# ===================================================================

@pytest.mark.asyncio
async def test_query_api_supports_session_only(ready_repo, session_seeded) -> None:
    from memoryx.api.query_api import MemoryQueryAPI
    vs = FakeVectorStore()
    api = MemoryQueryAPI(repository=ready_repo, vector_store=vs)
    results = await api.search(
        query="memory", query_vector=[],
        session_id="sess-A", session_only=True, limit=20,
    )
    texts = " ".join(r.get("content", "") for r in results)
    assert "Global fact" not in texts


# ===================================================================
# 11. Provider read supports session_only
# ===================================================================

@pytest.mark.asyncio
async def test_provider_read_supports_session_only(fake_bridge, ready_repo, session_seeded) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    # Read global memory with session_only=True -> should be filtered out
    result = await provider.handle_tool_call("memory", {"action": "read", "memory_id": "global-mem", "session_only": True}, "sess-A")
    assert result["ok"] is True
    assert result.get("filter_reason") == "session_only_filtered"


# ===================================================================
# 12. Provider list supports session_only
# ===================================================================

@pytest.mark.asyncio
async def test_provider_list_supports_session_only(fake_bridge, ready_repo, session_seeded) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "list", "session_only": True}, "sess-A")
    assert result["ok"] is True
    texts = " ".join(m.get("content", "") for m in result.get("memories", []))
    assert "Global fact" not in texts
    assert "User preference" not in texts
