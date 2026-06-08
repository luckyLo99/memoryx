"""DEPRECATED — moved to memoryx.graph.symbolic."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.symbolic is deprecated; use memoryx.graph.symbolic", DeprecationWarning, stacklevel=2)
from memoryx.graph.symbolic import SymbolicIndex
__all__ = ["SymbolicIndex"]
