"""Hermes agent integration layer for MemoryX."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from .bridge import HermesMemoryBridge, HermesBridgeResult
from .provider import MemoryXHermesProvider

__all__ = ["HermesMemoryBridge", "HermesBridgeResult", "MemoryXHermesProvider", "create_memory_provider"]


async def create_memory_provider(
    db_path: Path | str | None = None,
    vector_store: Any | None = None,
) -> MemoryXHermesProvider:
    """One-shot factory to create a fully wired MemoryXHermesProvider.

    This is the simplest way to integrate MemoryX with Hermes Agent:

        provider = await create_memory_provider()

    Args:
        db_path: Path to the SQLite database. If None, uses the default
            ``~/.hermes/memoryx/db/memoryx.sqlite3``.
        vector_store: Optional vector store for semantic search. If None,
            falls back to NullVectorProvider (FTS5 keyword search only).

    Returns:
        A ready-to-use MemoryXHermesProvider instance.
    """
    from memoryx.config import get_settings
    from memoryx.storage.repository import MemoryRepository
    from memoryx.api.query_api import MemoryQueryAPI
    from memoryx.embeddings.vector_store import NullVectorProvider
    from memoryx.working_memory.engine import WorkingMemoryEngine
    from memoryx.cognitive.attention_focus import AttentionFocusEngine
    from memoryx.safety.golden_rules import GoldenRuleEngine

    settings = get_settings()
    if db_path is None:
        db_path = settings.db_path
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    repo = MemoryRepository(db_path)
    await repo.open()

    if vector_store is None:
        vector_store = NullVectorProvider()

    # Initialize new cognitive systems
    working_memory = WorkingMemoryEngine(repository=repo, default_ttl_seconds=1800.0)
    attention_focus = AttentionFocusEngine(repository=repo)
    golden_rules = GoldenRuleEngine(repository=repo)
    await golden_rules.load_rules_from_db()

    query_api = MemoryQueryAPI(repository=repo, vector_store=vector_store)
    bridge = HermesMemoryBridge(
        repository=repo,
        query_api=query_api,
        working_memory_engine=working_memory,
        attention_focus_engine=attention_focus,
        golden_rule_engine=golden_rules,
    )
    return MemoryXHermesProvider(bridge=bridge)
