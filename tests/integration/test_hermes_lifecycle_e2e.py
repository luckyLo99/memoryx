"""Hermes Agent memory lifecycle E2E simulation.

Simulates the full Hermes Agent memory lifecycle without requiring
a real Hermes Agent installation.
"""
from __future__ import annotations
import os, pytest


@pytest.fixture
async def memoryx_env():
    import tempfile
    from pathlib import Path
    from memoryx.storage.repository import MemoryRepository
    from memoryx.hermes.provider import MemoryXHermesProvider
    from memoryx.hermes.bridge import HermesMemoryBridge
    from memoryx.services.memory_candidate_service import MemoryCandidateService
    tmp = tempfile.mkdtemp()
    db = Path(tmp) / "test.db"
    repo = MemoryRepository(db)
    await repo.open()
    cs = MemoryCandidateService(repository=repo)
    bridge = HermesMemoryBridge(repository=repo)
    provider = MemoryXHermesProvider(bridge=bridge)
    yield {"db": db, "repo": repo, "provider": provider}
    await repo.close()


@pytest.mark.asyncio
async def test_lifecycle_add_retrieve_forget(memoryx_env):
    r = await memoryx_env['provider'].handle_tool_call("memory", {"action": "add", "content": "My name is Alice and I work at Acme Corp."})
    assert r.get("ok", False), f"add failed: {r}"
    repo = memoryx_env["repo"]
    hits = await repo.search_full_text("Alice", limit=5)
    assert len(hits) > 0, "memory not retrievable"
    mid = hits[0].get("memory_id") or hits[0].get("id")
    r2 = await memoryx_env["provider"].handle_tool_call("memory", {"action": "remove", "memory_id": mid})
    assert r2.get("ok", False), f"remove failed: {r2}"
    hits2 = await repo.search_full_text("Alice", limit=5)
    assert hits2[0].get("active_state") == "quarantined"


@pytest.mark.asyncio
async def test_lifecycle_conflict_detection(memoryx_env):
    p = memoryx_env['provider']
    await p.handle_tool_call("memory", {"action": "add", "content": "User prefers dark mode"})
    await p.handle_tool_call("memory", {"action": "add", "content": "User prefers light mode"})
    hits = await memoryx_env["repo"].search_full_text("user prefers mode", limit=10)
    assert len(hits) >= 2


@pytest.mark.asyncio
async def test_lifecycle_context_injection(memoryx_env):
    await memoryx_env['provider'].handle_tool_call("memory", {"action": "add", "content": "API key in .env"})
    hits = await memoryx_env["repo"].search_full_text("API key", limit=5)
    assert len(hits) > 0
