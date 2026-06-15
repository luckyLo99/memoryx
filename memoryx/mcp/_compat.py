"""Compatibility re-exports from legacy memoryx.core for MCP."""
from __future__ import annotations
import warnings as _w
_w.warn("mcp._compat is deprecated; legacy bridge only", DeprecationWarning, stacklevel=2)
from memoryx.core.kernel import MemoryKernel as MemoryKernel  # noqa: E402
from memoryx.core.hermes_adapter import HermesAdapter as HermesAdapter  # noqa: E402
from memoryx.core.types import SearchOptions as SearchOptions  # noqa: E402
from memoryx.core.hybrid_retriever import HybridRetriever as HybridRetriever  # noqa: E402
__all__ = ["MemoryKernel", "HermesAdapter", "SearchOptions", "HybridRetriever"]
