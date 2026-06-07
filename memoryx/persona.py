"""DEPRECATED — moved to memoryx.cognitive.persona."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.persona is deprecated; use memoryx.cognitive.persona", DeprecationWarning, stacklevel=2)
from memoryx.cognitive.persona import PersonaEngine
__all__ = ["PersonaEngine"]
