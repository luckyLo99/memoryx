"""DEPRECATED - moved to memoryx.consolidation.llm_engine."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.llm_consolidation_engine is deprecated; use memoryx.consolidation.llm_engine", DeprecationWarning, stacklevel=2)
from memoryx.consolidation.llm_engine import LLMConsolidationEngine
__all__ = ["LLMConsolidationEngine"]
