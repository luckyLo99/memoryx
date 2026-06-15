"""DEPRECATED — moved to memoryx.reflection.reflect."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.reflect is deprecated; use memoryx.reflection.reflect", DeprecationWarning, stacklevel=2)
from memoryx.reflection.reflect import ReflectEngine  # noqa: E402
__all__ = ["ReflectEngine"]
