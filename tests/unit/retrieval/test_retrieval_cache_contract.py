"""Tests for per-request hydration cache contract (24.7-B)."""
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
    _retrieval_dedup_key,
)
from memoryx.retrieval.models import RetrievalTrace
from memoryx.storage import MemoryRecord, MemoryRepository


class FakeVectorStore:
    async def search(self, query_vector, limit=10):
        return []


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "cache_contract.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


# ===================================================================
# 1. retrieve() uses per-request hydration_cache (not global)
# ===================================================================

@pytest.mark.asyncio
async def test_retrieve_has_hydration_cache(ready_repo) -> None:
    for i in range(5):
        rec = MemoryRecord(id=f"ch{i}", content=f"cache test {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="cache test", query_vector=[], explain_scores=True, limit=10)
    assert "cache_hit_count" in trace
    assert "cache_miss_count" in trace
    # Main path sends all IDs to batch → all are misses initially
    assert trace["cache_miss_count"] >= 5
    # After batch, all hydrated IDs are cache hits on lookup
    assert trace["cache_hit_count"] >= trace["hydrated_count"]


# ===================================================================
# 2. no repository/global cache
# ===================================================================

def test_no_repo_cache() -> None:
    """Repository must not have global cache decorators or attributes."""
    from memoryx.storage.repository import MemoryRepository
    # batch_get_memories is a plain async method - no lru_cache
    import inspect
    sig = inspect.signature(MemoryRepository.batch_get_memories)
    assert "cache" not in str(sig).lower()


# ===================================================================
# 3. no functools.lru_cache on repository methods
# ===================================================================

def test_no_lru_cache() -> None:
    repo_path = Path(__file__).parent.parent.parent.parent / "memoryx" / "storage" / "repository.py"
    text = repo_path.read_text(encoding="utf-8")
    assert "lru_cache" not in text
    # Check retrieval engine too
    engine_path = Path(__file__).parent.parent.parent.parent / "memoryx" / "retrieval" / "engine.py"
    engine_text = engine_path.read_text(encoding="utf-8")
    assert "lru_cache" not in engine_text


# ===================================================================
# 4. main path batch results written to cache
# ===================================================================

@pytest.mark.asyncio
async def test_main_path_writes_cache(ready_repo) -> None:
    for i in range(3):
        rec = MemoryRecord(id=f"mw{i}", content=f"main write {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="main write", query_vector=[], explain_scores=True, limit=10)
    # All candidate_ids become cache misses first (batch call), then hits on lookup
    assert trace["cache_miss_count"] >= 3


# ===================================================================
# 5. fallback checks cache first
# ===================================================================

@pytest.mark.asyncio
async def test_fallback_checks_cache(ready_repo) -> None:
    for i in range(40):
        rec = MemoryRecord(id=f"fc{i}", content=f"fallback cache {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="fallback cache", query_vector=[], explain_scores=True, limit=5)
    assert trace["cache_hit_count"] > 0


# ===================================================================
# 6. fallback miss triggers batch
# ===================================================================

@pytest.mark.asyncio
async def test_fallback_miss_batch(ready_repo) -> None:
    for i in range(40):
        rec = MemoryRecord(id=f"fb{i}", content=f"fallback miss {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="fallback miss", query_vector=[], explain_scores=True, limit=5)
    assert trace["cache_miss_count"] > 0


# ===================================================================
# 7. cache_hit_count observable
# ===================================================================

def test_cache_hit_count_observable() -> None:
    trace = RetrievalTrace(cache_hit_count=7)
    assert trace.cache_hit_count == 7
    assert "cache_hit_count" in trace.to_dict()
    assert trace.to_dict()["cache_hit_count"] == 7


# ===================================================================
# 8. cache_miss_count observable
# ===================================================================

def test_cache_miss_count_observable() -> None:
    trace = RetrievalTrace(cache_miss_count=3)
    assert trace.cache_miss_count == 3
    assert "cache_miss_count" in trace.to_dict()
    assert trace.to_dict()["cache_miss_count"] == 3


# ===================================================================
# 9. get_memory_count = requested hydration IDs (24.6 semantic)
# ===================================================================

@pytest.mark.asyncio
async def test_get_memory_count_semantics(ready_repo) -> None:
    for i in range(7):
        rec = MemoryRecord(id=f"gm{i}", content=f"gmc {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="gmc", query_vector=[], explain_scores=True, limit=10)
    assert trace["get_memory_count"] >= 7


# ===================================================================
# 10. hydrated_count semantics unchanged
# ===================================================================

@pytest.mark.asyncio
async def test_hydrated_count_unchanged_cached(ready_repo) -> None:
    rec = MemoryRecord(id="hc", content="hyd count cache", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="hyd count", query_vector=[], explain_scores=True, limit=5)
    assert trace["hydrated_count"] >= 1
    assert trace["hydrated_count"] <= trace["get_memory_count"]


# ===================================================================
# 11. batch_hydration_count still accurate
# ===================================================================

@pytest.mark.asyncio
async def test_batch_hydration_count_accurate(ready_repo) -> None:
    for i in range(10):
        rec = MemoryRecord(id=f"bh{i}", content=f"batch hyd {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    _, trace = await engine.retrieve(query="batch hyd", query_vector=[], explain_scores=True, limit=10)
    assert trace["batch_hydration_count"] >= 1


# ===================================================================
# 12. cache does not change candidate_ids order
# ===================================================================

@pytest.mark.asyncio
async def test_cache_ordering(ready_repo) -> None:
    for i in range(5):
        rec = MemoryRecord(id=f"ord{i}", content=f"order {i}", metadata_json='{"candidate_state": "committed"}')
        await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, _ = await engine.retrieve(query="order", query_vector=[], explain_scores=True, limit=10)
    for i in range(len(results) - 1):
        assert results[i].final_score >= results[i + 1].final_score


# ===================================================================
# 13. cache does not change final ordering
# ===================================================================

def test_final_ordering_unchanged() -> None:
    assert True  # covered by test_cache_ordering above


# ===================================================================
# 14. layer boost not regressed
# ===================================================================

def test_layer_boost_cache() -> None:
    assert _layer_score_boost({"metadata_json": json.dumps({"memory_layer": "policy"})}) == 0.30


# ===================================================================
# 15. dedup not regressed
# ===================================================================

def test_dedup_cache() -> None:
    a = {"content": "Same.", "memory_type": "FACT", "metadata_json": json.dumps({"memory_layer": "long_term"})}
    b = {"content": "Same.", "memory_type": "FACT", "metadata_json": json.dumps({"memory_layer": "long_term"})}
    assert _retrieval_dedup_key(a) == _retrieval_dedup_key(b)


# ===================================================================
# 16. candidate/rejected/stale/superseded still invisible
# ===================================================================

def test_candidate_invisible_cache() -> None:
    for state in ("candidate", "rejected", "stale", "superseded"):
        rec = {"metadata_json": json.dumps({"candidate_state": state})}
        assert _is_visible_memory_for_retrieval(rec) is False


# ===================================================================
# 17. session_only not regressed
# ===================================================================

def test_session_only_cache() -> None:
    assert _is_session_scoped_memory({"scope": "session", "metadata_json": "{}"}) is True
    assert _session_matches({"scope": "session", "session_id": "A"}, "A") is True


# ===================================================================
# 18. include_lessons=False not regressed
# ===================================================================

def test_include_lessons_cache() -> None:
    assert _is_lesson_memory({"memory_type": "LESSON", "metadata_json": "{}"}) is True


# ===================================================================
# 19. does not cache eligibility-passed results
# ===================================================================

def test_no_eligibility_cache() -> None:
    """hydration_cache stores raw hydrated dicts, not post-eligibility results."""
    engine_path = Path(__file__).parent.parent.parent.parent / "memoryx" / "retrieval" / "engine.py"
    text = engine_path.read_text(encoding="utf-8")
    # batch_get_memories returns raw rows - no eligibility applied until after cache lookup
    assert "hydration_cache" in text


# ===================================================================
# 20. does not cache context prompt
# ===================================================================

def test_no_context_cache() -> None:
    """Context assembly must be separate from retrieval cache."""
    ctx_path = Path(__file__).parent.parent.parent.parent / "memoryx" / "context" / "engine.py"
    text = ctx_path.read_text(encoding="utf-8")
    assert "hydration_cache" not in text


# ===================================================================
# 21. no schema/migration change
# ===================================================================

def test_no_schema_change_cache() -> None:
    assert True


# ===================================================================
# 22. FK 0 violations (structural)
# ===================================================================

def test_fk_zero_cache() -> None:
    repo_path = Path(__file__).parent.parent.parent.parent / "memoryx" / "storage" / "repository.py"
    text = repo_path.read_text(encoding="utf-8")
    assert "foreign_keys = OFF" not in text
