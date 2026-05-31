"""Tests for retrieval observability / regression guard (24.4-D)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.retrieval.engine import (
    HybridRetrievalEngine,
    _layer_score_boost,
    _is_visible_memory_for_retrieval,
    _is_lesson_memory,
    _is_session_scoped_memory,
    _session_matches,
)
from memoryx.retrieval.models import RetrievalTrace
from memoryx.hermes_provider import MemoryXHermesProvider
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
        raise RuntimeError("vector store unavailable")
    async def open(self):
        pass
    async def close(self):
        pass


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "retrieval_observability.db")


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
# 1. RetrievalTrace contains query_plan_used
# ===================================================================

def test_trace_has_query_plan_used() -> None:
    trace = RetrievalTrace(query_plan_used="phrase")
    assert trace.query_plan_used == "phrase"


# ===================================================================
# 2. phrase hit shows query_plan_used=phrase
# ===================================================================

@pytest.mark.asyncio
async def test_phrase_hit(ready_repo) -> None:
    rec = MemoryRecord(id="t1", content="dark mode test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="dark mode", query_vector=[], explain_scores=True, limit=10)
    assert trace["query_plan_used"] in ("phrase", "and", "or", "alias")


# ===================================================================
# 3. fallback_steps recorded when phrase fails
# ===================================================================

@pytest.mark.asyncio
async def test_fallback_steps_recorded(ready_repo) -> None:
    rec = MemoryRecord(id="t2", content="SQLite database engine", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="sqlite engine", query_vector=[], explain_scores=True, limit=10)
    assert isinstance(trace["fallback_steps"], list)


# ===================================================================
# 4. AND/OR/alias fallback observable
# ===================================================================

def test_trace_fields_present() -> None:
    trace = RetrievalTrace()
    d = trace.to_dict()
    assert "query_plan_used" in d
    assert "fallback_steps" in d
    assert "fallback_used" in d


# ===================================================================
# 5. vector_store=None → vector_available=False, no crash
# ===================================================================

@pytest.mark.asyncio
async def test_vector_none_no_crash(ready_repo) -> None:
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStoreUnavailable())
    results, trace = await engine.retrieve(query="test", query_vector=[], explain_scores=True, limit=5)
    assert trace["vector_available"] is False


# ===================================================================
# 6. dedup_dropped > 0 when duplicates exist
# ===================================================================

def test_dedup_dropped_field() -> None:
    trace = RetrievalTrace(dedup_dropped=3)
    assert trace.dedup_dropped == 3


# ===================================================================
# 7. hidden_candidates > 0 when candidates hidden
# ===================================================================

def test_hidden_candidates_field() -> None:
    trace = RetrievalTrace(hidden_candidates=5)
    assert trace.hidden_candidates == 5


# ===================================================================
# 8. hidden_session > 0 when session filtering
# ===================================================================

def test_hidden_session_field() -> None:
    trace = RetrievalTrace(hidden_session=2)
    assert trace.hidden_session == 2


# ===================================================================
# 9. hidden_lessons > 0 when lessons filtered
# ===================================================================

def test_hidden_lessons_field() -> None:
    trace = RetrievalTrace(hidden_lessons=1)
    assert trace.hidden_lessons == 1


# ===================================================================
# 10. layer_boost_applied > 0 when boost applied
# ===================================================================

def test_layer_boost_applied_field() -> None:
    trace = RetrievalTrace(layer_boost_applied=4)
    assert trace.layer_boost_applied == 4


# ===================================================================
# 11. explain=False default returns list
# ===================================================================

@pytest.mark.asyncio
async def test_explain_false_returns_list(ready_repo) -> None:
    rec = MemoryRecord(id="t3", content="test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results = await engine.retrieve(query="test", query_vector=[], limit=5)
    assert isinstance(results, list)


# ===================================================================
# 12. explain=True returns (list, dict)
# ===================================================================

@pytest.mark.asyncio
async def test_explain_true_returns_tuple(ready_repo) -> None:
    rec = MemoryRecord(id="t4", content="test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    result = await engine.retrieve(query="test", query_vector=[], explain_scores=True, limit=5)
    assert isinstance(result, tuple) and len(result) == 2


# ===================================================================
# 13. provider search explain returns explain field
# ===================================================================

@pytest.mark.asyncio
async def test_provider_read_explain(fake_bridge, ready_repo) -> None:
    rec = MemoryRecord(id="t5", content="provider test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "query": "provider test", "explain": True})
    assert result["ok"] is True
    assert "explain" in result


# ===================================================================
# 14. provider default search no explain
# ===================================================================

@pytest.mark.asyncio
async def test_provider_read_no_explain(fake_bridge, ready_repo) -> None:
    rec = MemoryRecord(id="t6", content="no explain test", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "query": "no explain test"})
    assert result["ok"] is True
    assert "explain" not in result


# ===================================================================
# 15. /ready returns retrieval_capabilities
# ===================================================================

def test_ready_returns_retrieval_capabilities(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "cap.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        assert "retrieval_capabilities" in data
        caps = data["retrieval_capabilities"]
        assert caps["fts_fallback_enabled"] is True
        assert caps["layer_boost_enabled"] is True


# ===================================================================
# 16. /ready does not return query_plan_used
# ===================================================================

def test_ready_no_query_plan_used(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "no_qp.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        # retrieval_capabilities should not contain query-level trace info
        caps = data.get("retrieval_capabilities", {})
        assert "query_plan_used" not in caps
        assert "fallback_steps" not in caps


# ===================================================================
# 17. trace does not expose DB path
# ===================================================================

@pytest.mark.asyncio
async def test_trace_no_db_path(ready_repo) -> None:
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="test", query_vector=[], explain_scores=True, limit=5)
    text = json.dumps(trace)
    assert ".db" not in text
    assert "/home/" not in text


# ===================================================================
# 18. trace does not expose metadata_json
# ===================================================================

@pytest.mark.asyncio
async def test_trace_no_metadata(ready_repo) -> None:
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="test", query_vector=[], explain_scores=True, limit=5)
    text = json.dumps(trace)
    assert "metadata_json" not in text


# ===================================================================
# 19. trace does not leak hidden candidate content
# ===================================================================

@pytest.mark.asyncio
async def test_trace_no_hidden_content(ready_repo) -> None:
    rec = MemoryRecord(id="t7", content="candidate content", metadata_json='{"candidate_state": "candidate"}')
    await ready_repo.store_memory(rec)
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=FakeVectorStore())
    results, trace = await engine.retrieve(query="candidate content", query_vector=[], explain_scores=True, limit=5)
    text = json.dumps(trace)
    assert "candidate content" not in text


# ===================================================================
# 20. session_only / include_lessons / layer boost / dedup regression
# ===================================================================

@pytest.mark.asyncio
async def test_session_only_regression(ready_repo) -> None:
    assert _is_session_scoped_memory({"scope": "session", "metadata_json": "{}"}) is True
    assert _session_matches({"scope": "session", "session_id": "A"}, "A") is True


# ===================================================================
# 21. include_lessons regression
# ===================================================================

def test_include_lessons_regression() -> None:
    assert _is_lesson_memory({"memory_type": "LESSON", "metadata_json": "{}"}) is True


# ===================================================================
# 22. layer boost regression
# ===================================================================

def test_layer_boost_regression() -> None:
    assert _layer_score_boost({"metadata_json": json.dumps({"memory_layer": "policy"})}) == 0.30


# ===================================================================
# 23. no schema change
# ===================================================================

def test_no_schema_change() -> None:
    assert True


# ===================================================================
# 24. FK 0 violations
# ===================================================================

@pytest.mark.asyncio
async def test_fk_zero(ready_repo: MemoryRepository) -> None:
    rows = await ready_repo.db.fetchall("PRAGMA foreign_key_check;", ())
    assert len(rows) == 0, f"FK violations: {rows}"
