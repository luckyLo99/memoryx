"""DEPRECATED — moved to memoryx.hermes.bridge."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.hermes_bridge is deprecated; use memoryx.hermes.bridge", DeprecationWarning, stacklevel=2)
from memoryx.hermes.bridge import HermesMemoryBridge, HermesBridgeResult
__all__ = ["HermesMemoryBridge", "HermesBridgeResult"]
