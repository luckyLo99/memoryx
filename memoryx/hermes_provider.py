"""DEPRECATED — moved to memoryx.hermes.provider."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.hermes_provider is deprecated; use memoryx.hermes.provider", DeprecationWarning, stacklevel=2)
from memoryx.hermes.provider import MemoryXHermesProvider, _VALID_ACTIONS, _VALID_TARGETS, _DEFAULT_LIMIT, _MAX_LIMIT
__all__ = ["MemoryXHermesProvider", "_VALID_ACTIONS", "_VALID_TARGETS"]
