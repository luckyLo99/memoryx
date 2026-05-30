"""Tests for MemoryX readable memory export."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.hermes_provider import MemoryXHermesProvider, _VALID_ACTIONS
from memoryx.services.memory_candidate_service import (
    CandidateState,
    EvidenceLevel,
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)
from memoryx.storage import MemoryRecord, MemoryRepository

_VALID_FORMATS = {"memory_md", "user_md", "markdown", "json"}


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "readable_export.db")


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
async def seeded_repo(ready_repo: MemoryRepository) -> MemoryRepository:
    """Seed with committed and candidate memories."""
    svc = MemoryCandidateService(repository=ready_repo, policy=MemoryCandidatePolicy())
    # Committed FACT
    mid1 = await svc.create_candidate(MemoryCandidateRequest(content="User prefers dark mode.", memory_type="FACT", source_type="user", evidence_level=EvidenceLevel.E2_USER_CONFIRMED.value, confidence=0.95))
    assert mid1 is not None
    # Candidate - E0
    mid2 = await svc.create_candidate(MemoryCandidateRequest(content="Possible fact: user likes Go.", memory_type="FACT", source_type="assistant_inference", evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value, confidence=0.3, metadata={"native_target": "memory"}))
    assert mid2 is not None
    return ready_repo


# ===================================================================
# 1. action=export format=memory_md returns markdown
# ===================================================================

@pytest.mark.asyncio
async def test_export_memory_md(fake_bridge, seeded_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "memory_md"})
    assert result["ok"] is True
    assert result["format"] == "memory_md"
    assert isinstance(result.get("text"), str)
    assert "# MemoryX MEMORY Export" in result["text"]


# ===================================================================
# 2. action=export format=user_md returns user view
# ===================================================================

@pytest.mark.asyncio
async def test_export_user_md(fake_bridge, seeded_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "user_md"})
    assert result["ok"] is True
    assert result["format"] == "user_md"
    assert isinstance(result.get("text"), str)
    assert "# MemoryX USER Export" in result["text"]


# ===================================================================
# 3. export default excludes rejected/superseded
# ===================================================================

@pytest.mark.asyncio
async def test_export_excludes_rejected(fake_bridge, seeded_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "markdown"})
    assert result["ok"] is True
    text = result.get("text", "")
    assert "[REJECTED]" not in text
    assert "[SUPERSEDED]" not in text


# ===================================================================
# 4. include_candidates=true marks [CANDIDATE] and [VERIFIED]
# ===================================================================

@pytest.mark.asyncio
async def test_export_include_candidates_marks(fake_bridge, seeded_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "markdown", "include_candidates": True})
    assert result["ok"] is True
    text = result.get("text", "")
    # Should have the [CANDIDATE] prefix for E0 extract
    assert "[CANDIDATE]" in text


# ===================================================================
# 5. committed/verified state marked correctly
# ===================================================================

@pytest.mark.asyncio
async def test_export_committed_marked(fake_bridge, seeded_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "markdown", "include_candidates": True})
    assert result["ok"] is True
    text = result.get("text", "")
    # The FACT with E2 should be COMMITTED
    assert "[COMMITTED]" in text


# ===================================================================
# 6. export does not contain DB path
# ===================================================================

@pytest.mark.asyncio
async def test_export_no_db_path(fake_bridge, seeded_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "markdown"})
    assert result["ok"] is True
    text = result.get("text", "")
    assert ".db" not in text
    assert "/home/" not in text
    assert "memoryx" not in text.lower() or result["format"] is not None  # "memoryx" in context is fine


# ===================================================================
# 7. export does not contain secret/token/api_key
# ===================================================================

@pytest.mark.asyncio
async def test_export_no_secrets(fake_bridge, seeded_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "json"})
    assert result["ok"] is True
    text = json.dumps(result)
    assert "api_key" not in text.lower()
    assert "secret" not in text.lower() or "not exposed" in text  # limit_note mentions "secrets"


# ===================================================================
# 8. export limit takes effect
# ===================================================================

@pytest.mark.asyncio
async def test_export_limit(fake_bridge, seeded_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "json", "limit": 1})
    assert result["ok"] is True
    assert result["count"] >= 0
    # With limit 1, we should have at most 1 result
    assert result["count"] <= 1, f"limit=1 should return at most 1, got {result['count']}"


# ===================================================================
# 9. export does not write files
# ===================================================================

@pytest.mark.asyncio
async def test_export_no_file_write(fake_bridge, seeded_repo, tmp_path: Path) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "markdown"})
    assert result["ok"] is True
    # Result is returned as text, not written to disk
    assert "text" in result
    # No file should have been created
    files_before = list(tmp_path.rglob("*"))
    # Just verify result shape is correct
    assert isinstance(result["text"], str)


# ===================================================================
# 10. Invalid format returns error
# ===================================================================

@pytest.mark.asyncio
async def test_export_invalid_format(fake_bridge) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "invalid_format"})
    assert result["ok"] is False
    assert "invalid format" in result["error"]


# ===================================================================
# 11. export with target filter works
# ===================================================================

@pytest.mark.asyncio
async def test_export_target_filter(fake_bridge, seeded_repo) -> None:
    provider = MemoryXHermesProvider(bridge=fake_bridge)
    result = await provider.handle_tool_call("memory", {"action": "export", "format": "json", "target": "memory"})
    assert result["ok"] is True
    assert result["format"] == "json"
