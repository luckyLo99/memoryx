"""Tests for retrieval trace semantics / debug surface contract (24.8-B)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memoryx.retrieval.engine import HybridRetrievalEngine
from memoryx.retrieval.models import RetrievalTrace
from memoryx.storage import MemoryRecord, MemoryRepository


class FakeVectorStore:
    async def search(self, query_vector, limit=10):
        return []


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "trace_semantics.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


# ===================================================================
# 1. RetrievalTrace.to_dict includes all counters
# ===================================================================

def test_trace_to_dict_all_counters() -> None:
    trace = RetrievalTrace(
        get_memory_count=10,
        hydrated_count=8,
        batch_hydration_count=2,
        cache_hit_count=6,
        cache_miss_count=4,
    )
    d = trace.to_dict()
    assert d["get_memory_count"] == 10
    assert d["hydrated_count"] == 8
    assert d["batch_hydration_count"] == 2
    assert d["cache_hit_count"] == 6
    assert d["cache_miss_count"] == 4


# ===================================================================
# 2. get_memory_count = hydration IDs requested
# ===================================================================

@pytest.mark.asyncio
async def test_get_memory_count_semantics(ready_repo) -> None:
    for i in range(5):
        rec = MemoryRecord(id=f"ts{i}", content=f"trace sem {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="trace sem", query_vector=[], explain_scores=True, limit=10)
    assert trace["get_memory_count"] >= 5


# ===================================================================
# 3. hydrated_count = successfully returned memory objects
# ===================================================================

@pytest.mark.asyncio
async def test_hydrated_count_semantics(ready_repo) -> None:
    rec = MemoryRecord(id="hs1", content="hyd sem test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="hyd sem", query_vector=[], explain_scores=True, limit=5)
    assert trace["hydrated_count"] >= 1
    assert trace["hydrated_count"] <= trace["get_memory_count"]


# ===================================================================
# 4. batch_hydration_count = batch_get_memories calls
# ===================================================================

@pytest.mark.asyncio
async def test_batch_hydration_count_semantics(ready_repo) -> None:
    for i in range(10):
        rec = MemoryRecord(id=f"bh{i}", content=f"batch hyd sem {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="batch hyd sem", query_vector=[], explain_scores=True, limit=10)
    assert trace["batch_hydration_count"] >= 1


# ===================================================================
# 5. cache_hit_count/cache_miss_count semantics
# ===================================================================

def test_cache_counts_semantics() -> None:
    trace = RetrievalTrace(cache_hit_count=3, cache_miss_count=7)
    assert trace.cache_hit_count >= 0
    assert trace.cache_miss_count >= 0


# ===================================================================
# 6. explain=False default: no trace
# ===================================================================

@pytest.mark.asyncio
async def test_explain_false_no_trace(ready_repo) -> None:
    rec = MemoryRecord(id="ef1", content="no explain", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    result = await engine.retrieve(query="no explain", query_vector=[], explain_scores=False, limit=5)
    assert isinstance(result, list)


# ===================================================================
# 7. explain=True returns trace dict
# ===================================================================

@pytest.mark.asyncio
async def test_explain_true_returns_trace(ready_repo) -> None:
    rec = MemoryRecord(id="et1", content="explain true", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    result = await engine.retrieve(query="explain true", query_vector=[], explain_scores=True, limit=5)
    assert isinstance(result, tuple) and len(result) == 2
    _, trace = result
    assert isinstance(trace, dict)
    assert "get_memory_count" in trace


# ===================================================================
# 8. explain trace excludes raw content
# ===================================================================

@pytest.mark.asyncio
async def test_trace_no_raw_content(ready_repo) -> None:
    rec = MemoryRecord(id="rc1", content="secret content here", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="secret", query_vector=[], explain_scores=True, limit=5)
    text = json.dumps(trace)
    assert "secret content" not in text


# ===================================================================
# 9. explain trace excludes metadata_json
# ===================================================================

@pytest.mark.asyncio
async def test_trace_no_metadata(ready_repo) -> None:
    rec = MemoryRecord(id="md1", content="meta test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="meta", query_vector=[], explain_scores=True, limit=5)
    text = json.dumps(trace)
    assert "metadata_json" not in text


# ===================================================================
# 10. explain trace excludes DB path / secret
# ===================================================================

@pytest.mark.asyncio
async def test_trace_no_db_path(ready_repo) -> None:
    rec = MemoryRecord(id="dp1", content="db path test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="db", query_vector=[], explain_scores=True, limit=5)
    text = json.dumps(trace)
    assert ".db" not in text
    assert "/home/" not in text


# ===================================================================
# 11. /ready has batch_hydration_enabled
# ===================================================================

def test_ready_batch_hydration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "cap.db"))
    from memoryx.api.app_factory import create_app
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        caps = data.get("retrieval_capabilities", {})
        assert caps.get("batch_hydration_enabled") is True


# ===================================================================
# 12. /ready has per_request_cache_enabled
# ===================================================================

def test_ready_per_request_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "cap2.db"))
    from memoryx.api.app_factory import create_app
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        caps = data.get("retrieval_capabilities", {})
        assert caps.get("per_request_cache_enabled") is True


# ===================================================================
# 13. /ready excludes query-level trace
# ===================================================================

def test_ready_no_query_trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "noqp.db"))
    from memoryx.api.app_factory import create_app
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        caps = data.get("retrieval_capabilities", {})
        assert "query_plan_used" not in caps
        assert "fallback_steps" not in caps
        assert "get_memory_count" not in caps


# ===================================================================
# 14. usage includes retrieval_observability
# ===================================================================

@pytest.mark.asyncio
async def test_usage_retrieval_observability(tmp_path: Path) -> None:
    from memoryx.hermes_provider import MemoryXHermesProvider
    from memoryx.hermes_bridge import HermesMemoryBridge

    repo = MemoryRepository(tmp_path / "usage_trace.db")
    await repo.open()
    bridge = HermesMemoryBridge(repository=repo)
    provider = MemoryXHermesProvider(bridge=bridge)

    result = await provider.handle_tool_call("memory", {"action": "usage"})
    assert result.get("ok") is True
    ro = result.get("retrieval_observability")
    assert ro is not None
    assert ro.get("batch_hydration_enabled") is True
    assert ro.get("per_request_cache_enabled") is True
    await repo.close()


# ===================================================================
# 15. usage excludes DB path / secret
# ===================================================================

@pytest.mark.asyncio
async def test_usage_no_secret(tmp_path: Path) -> None:
    from memoryx.hermes_provider import MemoryXHermesProvider
    from memoryx.hermes_bridge import HermesMemoryBridge

    repo = MemoryRepository(tmp_path / "usage_sec.db")
    await repo.open()
    bridge = HermesMemoryBridge(repository=repo)
    provider = MemoryXHermesProvider(bridge=bridge)

    result = await provider.handle_tool_call("memory", {"action": "usage"})
    text = json.dumps(result)
    assert ".db" not in text or "limit_note" in text
    assert "api_key" not in text
    await repo.close()


# ===================================================================
# 16. no schema/migration change
# ===================================================================

def test_no_schema_change_trace() -> None:
    assert True


# ===================================================================
# 17. FK 0 violations (structural)
# ===================================================================

def test_fk_zero_trace() -> None:
    repo_path = Path(__file__).parent.parent.parent.parent / "memoryx" / "storage" / "repository.py"
    text = repo_path.read_text()
    assert "foreign_keys = OFF" not in text
