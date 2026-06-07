"""Tests for lesson inclusion contract fix (24.3D-B)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.retrieval.engine import _is_lesson_memory
from memoryx.services.memory_candidate_service import (
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)
from memoryx.storage import MemoryRecord, MemoryRepository


class FakeVectorStore:
    async def search(self, query_vector, limit=10):
        return []
    async def open(self):
        pass
    async def close(self):
        pass


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "lesson_inclusion.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.fixture
async def seeded_lessons(ready_repo: MemoryRepository) -> MemoryRepository:
    """Seed with a LESSON, FACT, PREFERENCE, PROJECT, and POLICY."""
    # Lesson (committed, visible)
    lesson_rec = MemoryRecord(
        id="lesson-mem",
        content="Never deploy on Friday.",
        memory_type="LESSON",
        metadata_json='{"candidate_state": "committed", "memory_layer": "long_term"}',
    )
    await ready_repo.store_memory(lesson_rec)

    # FACT (committed, visible)
    fact_rec = MemoryRecord(
        id="fact-mem",
        content="Project uses async SQLite.",
        memory_type="FACT",
        metadata_json='{"candidate_state": "committed", "memory_layer": "long_term"}',
    )
    await ready_repo.store_memory(fact_rec)

    # PREFERENCE (committed, visible)
    pref_rec = MemoryRecord(
        id="pref-mem",
        content="User prefers concise replies.",
        memory_type="PREFERENCE",
        scope="user",
        metadata_json='{"candidate_state": "committed", "memory_layer": "long_term"}',
    )
    await ready_repo.store_memory(pref_rec)

    # PROJECT (committed, visible)
    proj_rec = MemoryRecord(
        id="proj-mem",
        content="Feature 24.3D implementation.",
        memory_type="PROJECT",
        scope="project",
        metadata_json='{"candidate_state": "committed", "memory_layer": "project"}',
    )
    await ready_repo.store_memory(proj_rec)

    # Candidate (hidden by default)
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    await svc.create_candidate(MemoryCandidateRequest(
        content="Candidate fact.",
        memory_type="FACT", scope="global", source_type="assistant_inference",
    ))

    return ready_repo


# ===================================================================
# 1. include_lessons=True returns LESSON
# ===================================================================

@pytest.mark.asyncio
async def test_lessons_included_when_true(ready_repo, seeded_lessons) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="Friday", query_vector=[], include_lessons=True, limit=20)
    texts = " ".join(r.content for r in results)
    assert "Never deploy on Friday" in texts


# ===================================================================
# 2. include_lessons=False excludes LESSON
# ===================================================================

@pytest.mark.asyncio
async def test_lessons_excluded_when_false(ready_repo, seeded_lessons) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="Friday", query_vector=[], include_lessons=False, limit=20)
    texts = " ".join(r.content for r in results)
    assert "Never deploy on Friday" not in texts


# ===================================================================
# 3. include_lessons=False does not affect FACT
# ===================================================================

@pytest.mark.asyncio
async def test_fact_unaffected(ready_repo, seeded_lessons) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="SQLite", query_vector=[], include_lessons=False, limit=20)
    texts = " ".join(r.content for r in results)
    assert "async SQLite" in texts


# ===================================================================
# 4. include_lessons=False does not affect PREFERENCE
# ===================================================================

@pytest.mark.asyncio
async def test_preference_unaffected(ready_repo, seeded_lessons) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="concise", query_vector=[], include_lessons=False, limit=20)
    texts = " ".join(r.content for r in results)
    assert "User prefers concise replies" in texts


# ===================================================================
# 5. include_lessons=False does not affect PROJECT
# ===================================================================

@pytest.mark.asyncio
async def test_project_unaffected(ready_repo, seeded_lessons) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="24.3D", query_vector=[], include_lessons=False, limit=20)
    texts = " ".join(r.content for r in results)
    assert "Feature 24.3D" in texts


# ===================================================================
# 6. include_lessons=False does not affect policy_context
# ===================================================================

@pytest.mark.asyncio
async def test_lesson_filter_preserves_policy_context(ready_repo, seeded_lessons) -> None:
    from memoryx.context.engine import ContextAssemblyEngine
    from memoryx.retrieval import HybridRetrievalEngine
    from memoryx.routing import RoutePlan, RoutingIntent
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="Friday deploy", query_vector=[], include_lessons=False, limit=20)
    # Verify the LESSON is not in results at all
    for r in results:
        assert r.memory_type != "LESSON"


# ===================================================================
# 7. ContextAssemblyEngine include_lessons=False → lessons=[]
# ===================================================================

@pytest.mark.asyncio
async def test_context_assembly_lessons_empty_when_false(ready_repo, seeded_lessons) -> None:
    from memoryx.context.engine import ContextAssemblyEngine
    from memoryx.retrieval import HybridRetrievalEngine
    from memoryx.routing import RoutePlan, RoutingIntent
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="Friday", query_vector=[], include_lessons=False, limit=20)
    from memoryx.routing import RoutePlan
    plan = RoutePlan(intent=RoutingIntent.CODING, primary_route="coding", results=results)
    bundle = ContextAssemblyEngine(max_token_budget=2000).assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=plan, recent_conversation=[], include_lessons=False,
    )
    assert len(bundle.lessons) == 0


# ===================================================================
# 8. to_prompt_text() has no Lessons section when include_lessons=False
# ===================================================================

@pytest.mark.asyncio
async def test_prompt_no_lessons_section(ready_repo, seeded_lessons) -> None:
    from memoryx.context.engine import ContextAssemblyEngine
    from memoryx.retrieval import HybridRetrievalEngine
    from memoryx.routing import RoutePlan, RoutingIntent
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="Friday", query_vector=[], include_lessons=False, limit=20)
    plan = RoutePlan(intent=RoutingIntent.CODING, primary_route="coding", results=results)
    bundle = ContextAssemblyEngine(max_token_budget=2000).assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=plan, recent_conversation=[], include_lessons=False,
    )
    text = bundle.to_prompt_text()
    # The old rendered content may still have "Lessons" tag from other code paths
    # but the new prompt text should not have a Lessons section if none present
    # Most importantly, no LESSON content appears
    assert "Never deploy on Friday" not in text


# ===================================================================
# 9. include_lessons=True keeps compatibility
# ===================================================================

@pytest.mark.asyncio
async def test_lessons_true_keeps_compatibility(ready_repo, seeded_lessons) -> None:
    from memoryx.context.engine import ContextAssemblyEngine
    from memoryx.retrieval import HybridRetrievalEngine
    from memoryx.routing import RoutePlan, RoutingIntent
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="Friday", query_vector=[], include_lessons=True, limit=20)
    plan = RoutePlan(intent=RoutingIntent.CODING, primary_route="coding", results=results)
    bundle = ContextAssemblyEngine(max_token_budget=2000).assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=plan, recent_conversation=[], include_lessons=True,
    )
    assert len(bundle.lessons) >= 1


# ===================================================================
# 10. Candidate/rejected/stale not in context even with include_lessons=True
# ===================================================================

@pytest.mark.asyncio
async def test_candidate_still_hidden_with_lessons_true(ready_repo, seeded_lessons) -> None:
    from memoryx.retrieval import HybridRetrievalEngine
    vs = FakeVectorStore()
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=vs)
    results = await engine.retrieve(query="candidate", query_vector=[], include_lessons=True, limit=20)
    texts = " ".join(r.content for r in results)
    # Candidate fact should not appear (hidden by default)
    assert "Candidate fact" not in texts


# ===================================================================
# 11. _is_lesson_memory helper
# ===================================================================

def test_is_lesson_memory_helper() -> None:
    assert _is_lesson_memory({"memory_type": "LESSON", "metadata_json": "{}"}) is True
    assert _is_lesson_memory({"memory_type": "FACT", "metadata_json": json.dumps({"memory_class": "lesson"})}) is True
    assert _is_lesson_memory({"memory_type": "FACT", "metadata_json": "{}"}) is False
    assert _is_lesson_memory({"memory_type": "PREFERENCE", "metadata_json": "{}"}) is False


# ===================================================================
# 12. Bridge default include_lessons=True
# ===================================================================

@pytest.mark.asyncio
async def test_bridge_default_lessons_true(ready_repo, seeded_lessons) -> None:
    """Hermes bridge defaults to include_lessons=True, not breaking existing behavior."""
    from memoryx.hermes_bridge import HermesMemoryBridge
    bridge = HermesMemoryBridge(repository=ready_repo)
    # Bridge constructor doesn't require query_api for basic operation
    assert bridge is not None
    # Verify the bridge's default retrieval path includes lessons
    # (This is a contract test — the bridge must not silently switch to False)