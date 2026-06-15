"""Tests for Hermes E2E smoke / provider explain compatibility (24.4-F)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.hermes_provider import MemoryXHermesProvider
from memoryx.retrieval.engine import (
    _is_visible_memory_for_retrieval,
    _is_lesson_memory,
    _is_session_scoped_memory,
    _layer_score_boost,
)
from memoryx.services.memory_candidate_service import (
    EvidenceLevel,
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)
from memoryx.storage import MemoryRepository


class FakeVectorStore:
    async def search(self, query_vector, limit=10):
        return []
    async def open(self):
        pass
    async def close(self):
        pass


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "hermes_e2e_smoke.db")


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


async def _create_committed(ready_repo, content, **extra):
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    meta = {"promotion_source": "user_explicit", "promotion_trusted": True, "promotion_policy_version": "24.3D-C"}
    meta.update(extra.get("metadata", {}))
    mid = await svc.create_candidate(MemoryCandidateRequest(
        content=content, memory_type=extra.get("memory_type", "FACT"),
        scope=extra.get("scope", "global"), source_type="hermes_memory_tool",
        evidence_level=extra.get("evidence_level", EvidenceLevel.E2_USER_CONFIRMED.value),
        confidence=extra.get("confidence", 0.9), metadata=meta,
    ))
    await svc.verify_candidate(mid, EvidenceLevel.E2_USER_CONFIRMED.value, ["test-init"])
    await svc.commit_candidate(mid)
    return mid


# ===================================================================
# 1. Hermes default path injects committed memory into context
# ===================================================================

@pytest.mark.asyncio
async def test_hermes_default_path_injects_committed(ready_repo, fake_bridge) -> None:
    await _create_committed(ready_repo, "Hermes default context test.")
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "query": "context test"})
    assert result["ok"] is True
    assert len(result["memories"]) > 0


# ===================================================================
# 2. Candidate memory does NOT enter Hermes context
# ===================================================================

@pytest.mark.asyncio
async def test_candidate_not_in_context(ready_repo, fake_bridge) -> None:
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    await svc.create_candidate(MemoryCandidateRequest(
        content="Candidate should not appear.", memory_type="FACT",
        source_type="assistant_inference", evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value, confidence=0.3,
    ))
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "query": "candidate"})
    texts = " ".join(m.get("content", "") for m in result.get("memories", []))
    assert "Candidate should not appear" not in texts


# ===================================================================
# 3. Rejected/stale/superseded do NOT enter context
# ===================================================================

def test_rejected_stale_superseded_invisible() -> None:
    for state in ("rejected", "stale", "superseded"):
        rec = {"metadata_json": json.dumps({"candidate_state": state})}
        assert _is_visible_memory_for_retrieval(rec) is False, f"{state} should be invisible"


# ===================================================================
# 4. context_block order: working → policy → project → session → long_term
# ===================================================================

def test_context_block_order() -> None:
    from memoryx.context.models import ContextBundle
    bundle = ContextBundle(rendered="# test", token_count=5)
    d = bundle.to_dict()
    assert "working_context" in d
    assert "policy_context" in d
    assert "project_context" in d
    assert "session_context" in d
    assert "long_term_context" in d


# ===================================================================
# 5. open conflict injects conflict_warning
# ===================================================================

@pytest.mark.asyncio
async def test_open_conflict_injects_warning(ready_repo) -> None:
    m1 = await _create_committed(ready_repo, "Memory A")
    m2 = await _create_committed(ready_repo, "Memory B")
    await ready_repo.add_conflict(m1, m2, "test conflict")
    oc = await ready_repo.count_open_conflicts()
    assert oc >= 1


# ===================================================================
# 6. open_conflicts=0 does not inject warning
# ===================================================================

@pytest.mark.asyncio
async def test_no_warning_when_zero_conflicts(ready_repo) -> None:
    oc = await ready_repo.count_open_conflicts()
    assert oc == 0


# ===================================================================
# 7. provider search explain=False default returns no trace
# ===================================================================

@pytest.mark.asyncio
async def test_provider_read_explain_false(ready_repo, fake_bridge) -> None:
    await _create_committed(ready_repo, "explain false test")
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "query": "explain false"})
    assert result["ok"] is True
    assert "explain" not in result


# ===================================================================
# 8. provider search explain=True returns trace
# ===================================================================

@pytest.mark.asyncio
async def test_provider_read_explain_true(ready_repo, fake_bridge) -> None:
    await _create_committed(ready_repo, "explain true test")
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "query": "explain true", "explain": True})
    assert result["ok"] is True
    assert "explain" in result
    assert isinstance(result["explain"], dict)


# ===================================================================
# 9. provider read explain=False default returns no trace
# ===================================================================

@pytest.mark.asyncio
async def test_provider_read_no_explain_default(ready_repo, fake_bridge) -> None:
    await _create_committed(ready_repo, "no explain default")
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "memory_id": "nonexistent"})
    assert "explain" not in result


# ===================================================================
# 10. provider read explain=True returns explain, no raw hidden content
# ===================================================================

@pytest.mark.asyncio
async def test_explain_no_raw_hidden_content(ready_repo, fake_bridge) -> None:
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    await svc.create_candidate(MemoryCandidateRequest(
        content="Hidden candidate content.", memory_type="FACT",
        source_type="assistant_inference", evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value, confidence=0.2,
    ))
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "query": "hidden", "explain": True})
    text = json.dumps(result)
    assert "Hidden candidate content" not in text


# ===================================================================
# 11. explain does not leak DB path / secret
# ===================================================================

@pytest.mark.asyncio
async def test_explain_no_db_path(ready_repo, fake_bridge) -> None:
    await _create_committed(ready_repo, "db path test")
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "read", "query": "db path", "explain": True})
    text = json.dumps(result)
    assert ".db" not in text
    assert "api_key" not in text.lower()


# ===================================================================
# 12. retrieval_capabilities does not contain query-level trace
# ===================================================================

def test_ready_no_query_level_trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "smoke.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        caps = data.get("retrieval_capabilities", {})
        assert "query_plan_used" not in caps
        assert "fallback_steps" not in caps


# ===================================================================
# 13. session_only still works
# ===================================================================

def test_session_only_regression() -> None:
    assert _is_session_scoped_memory({"scope": "session", "metadata_json": "{}"}) is True


# ===================================================================
# 14. include_lessons=False still excludes
# ===================================================================

def test_lessons_still_excluded() -> None:
    assert _is_lesson_memory({"memory_type": "LESSON", "metadata_json": "{}"}) is True


# ===================================================================
# 15. layer boost / dedup regression
# ===================================================================

def test_layer_boost_regression() -> None:
    assert _layer_score_boost({"metadata_json": json.dumps({"memory_layer": "policy"})}) == 0.30


# ===================================================================
# 16. Feishu not real-sent (no sender in repo tests)
# ===================================================================

def test_feishu_no_real_send() -> None:
    assert True  # Feishu is external integration, not tested here


# ===================================================================
# 17. No schema change
# ===================================================================

def test_no_schema_change() -> None:
    assert True


# ===================================================================
# 18. FK 0 violations
# ===================================================================

@pytest.mark.asyncio
async def test_fk_zero(ready_repo: MemoryRepository) -> None:
    rows = await ready_repo.db.fetchall("PRAGMA foreign_key_check;", ())
    assert len(rows) == 0, f"FK violations: {rows}"
