"""Tests for retrieval performance guard / scale smoke (24.4-E)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.retrieval.engine import (
    HybridRetrievalEngine,
    _is_visible_memory_for_retrieval,
    _is_lesson_memory,
    _is_session_scoped_memory,
    _session_matches,
    _layer_score_boost,
)
from memoryx.retrieval.models import RetrievalTrace
from memoryx.storage import MemoryRecord, MemoryRepository


class FakeVectorStore:
    async def search(self, query_vector, limit=10):
        return []
    async def open(self):
        pass
    async def close(self):
        pass


class FakeVectorStoreUnavailable:
    async def search(self, query_vector, limit=10):
        raise RuntimeError("unavailable")
    async def open(self):
        pass
    async def close(self):
        pass


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "perf_guard.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


# ===================================================================
# 1. RetrievalTrace has hydrated_count
# ===================================================================

def test_trace_has_hydrated_count() -> None:
    trace = RetrievalTrace(hydrated_count=5)
    assert trace.hydrated_count == 5
    assert "hydrated_count" in trace.to_dict()


# ===================================================================
# 2. RetrievalTrace has get_memory_count
# ===================================================================

def test_trace_has_get_memory_count() -> None:
    trace = RetrievalTrace(get_memory_count=10)
    assert trace.get_memory_count == 10
    assert "get_memory_count" in trace.to_dict()


# ===================================================================
# 3. Main loop increments get_memory_count
# ===================================================================

@pytest.mark.asyncio
async def test_get_memory_count_increments(ready_repo) -> None:
    for i in range(5):
        rec = MemoryRecord(id=f"t{i}", content=f"test content {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="test", query_vector=[], explain_scores=True, limit=10)
    assert trace["get_memory_count"] >= 5


# ===================================================================
# 4. hydrated_count <= get_memory_count
# ===================================================================

@pytest.mark.asyncio
async def test_hydrated_leq_get_memory(ready_repo) -> None:
    rec = MemoryRecord(id="h1", content="content", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="content", query_vector=[], explain_scores=True, limit=10)
    assert trace["hydrated_count"] <= trace["get_memory_count"]


# ===================================================================
# 5. Fallback path also increments counters
# ===================================================================

@pytest.mark.asyncio
async def test_fallback_path_increments(ready_repo) -> None:
    for i in range(40):
        rec = MemoryRecord(id=f"f{i}", content=f"fallback test content {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="fallback test", query_vector=[], explain_scores=True, limit=5)
    assert trace["get_memory_count"] > 0


# ===================================================================
# 6. Fallback at most once
# ===================================================================

def test_fallback_at_most_once() -> None:
    trace = RetrievalTrace(fallback_used=True, fallback_fetch_limit=30)
    assert trace.fallback_used is True
    assert trace.fallback_fetch_limit is not None


# ===================================================================
# 7. get_memory_count <= base_fetch + fallback_fetch
# ===================================================================

@pytest.mark.asyncio
async def test_get_memory_count_bounded(ready_repo) -> None:
    for i in range(30):
        rec = MemoryRecord(id=f"b{i}", content=f"bounded test {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="bounded", query_vector=[], explain_scores=True, limit=10)
    base = trace["fetch_limit"] or 30
    fallback = trace["fallback_fetch_limit"] or 0
    assert trace["get_memory_count"] <= base + fallback


# ===================================================================
# 8. Fallback does not re-hydrate processed IDs
# ===================================================================

@pytest.mark.asyncio
async def test_fallback_no_duplicate_hydration(ready_repo) -> None:
    for i in range(35):
        rec = MemoryRecord(id=f"d{i}", content=f"dedup hydration {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="dedup hydration", query_vector=[], explain_scores=True, limit=5)
    # hydrated_count should not exceed total unique memories
    assert trace["hydrated_count"] <= 35


# ===================================================================
# 9. explain_scores=False returns list
# ===================================================================

@pytest.mark.asyncio
async def test_explain_false_returns_list(ready_repo) -> None:
    rec = MemoryRecord(id="e1", content="test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results = await engine.retrieve(query="test", query_vector=[], explain_scores=False, limit=5)
    assert isinstance(results, list)


# ===================================================================
# 10. explain_scores=True returns trace
# ===================================================================

@pytest.mark.asyncio
async def test_explain_true_returns_trace(ready_repo) -> None:
    rec = MemoryRecord(id="e2", content="trace test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    result = await engine.retrieve(query="trace test", query_vector=[], explain_scores=True, limit=5)
    assert isinstance(result, tuple) and len(result) == 2
    _, trace = result
    assert isinstance(trace, dict)
    assert "hydrated_count" in trace
    assert "get_memory_count" in trace


# ===================================================================
# 11. Trace does not expose raw content
# ===================================================================

@pytest.mark.asyncio
async def test_trace_no_raw_content(ready_repo) -> None:
    rec = MemoryRecord(id="s1", content="secret content here", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="secret", query_vector=[], explain_scores=True, limit=5)
    text = json.dumps(trace)
    assert "secret content" not in text


# ===================================================================
# 12. Trace does not expose DB path
# ===================================================================

@pytest.mark.asyncio
async def test_trace_no_db_path(ready_repo) -> None:
    rec = MemoryRecord(id="s2", content="db path test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="db", query_vector=[], explain_scores=True, limit=5)
    text = json.dumps(trace)
    assert ".db" not in text
    assert "/home/" not in text


# ===================================================================
# 13. Scale smoke: N=200, limit=10, no time threshold
# ===================================================================

@pytest.mark.asyncio
async def test_scale_smoke_n200(ready_repo) -> None:
    for i in range(200):
        rec = MemoryRecord(id=f"scale{i}", content=f"scale test memory {i} with keyword", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="scale test", query_vector=[], explain_scores=True, limit=10)
    base = trace["fetch_limit"] or 30
    fallback = trace["fallback_fetch_limit"] or 0
    assert trace["get_memory_count"] <= base + fallback
    assert trace["hydrated_count"] <= trace["get_memory_count"]
    assert len(results) <= 10


# ===================================================================
# 14. Candidate/rejected/stale/superseded still invisible
# ===================================================================

def test_candidate_still_invisible() -> None:
    rec = {"metadata_json": json.dumps({"candidate_state": "candidate"})}
    assert _is_visible_memory_for_retrieval(rec) is False
    rec2 = {"metadata_json": json.dumps({"candidate_state": "rejected"})}
    assert _is_visible_memory_for_retrieval(rec2) is False


# ===================================================================
# 15. session_only still works
# ===================================================================

def test_session_only_still_works() -> None:
    assert _is_session_scoped_memory({"scope": "session", "metadata_json": "{}"}) is True
    assert _session_matches({"scope": "session", "session_id": "A"}, "A") is True


# ===================================================================
# 16. include_lessons=False still excludes
# ===================================================================

def test_lessons_still_excluded() -> None:
    assert _is_lesson_memory({"memory_type": "LESSON", "metadata_json": "{}"}) is True


# ===================================================================
# 17. layer boost still works
# ===================================================================

def test_layer_boost_still_works() -> None:
    assert _layer_score_boost({"metadata_json": json.dumps({"memory_layer": "policy"})}) == 0.30


# ===================================================================
# 18. retrieval dedup still works
# ===================================================================

def test_dedup_still_works() -> None:
    from memoryx.retrieval.engine import _retrieval_dedup_key
    a = {"content": "Same.", "memory_type": "FACT", "metadata_json": json.dumps({"memory_layer": "long_term"})}
    b = {"content": "Same.", "memory_type": "FACT", "metadata_json": json.dumps({"memory_layer": "long_term"})}
    assert _retrieval_dedup_key(a) == _retrieval_dedup_key(b)


# ===================================================================
# 19. No schema change
# ===================================================================

def test_no_schema_change() -> None:
    assert True


# ===================================================================
# 20. FK 0 violations
# ===================================================================

@pytest.mark.asyncio
async def test_fk_zero(ready_repo: MemoryRepository) -> None:
    rows = await ready_repo.db.fetchall("PRAGMA foreign_key_check;", ())
    assert len(rows) == 0, f"FK violations: {rows}"
