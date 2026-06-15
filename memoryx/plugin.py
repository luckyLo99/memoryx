"""DEPRECATED - moved to memoryx.api.plugin."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.plugin is deprecated; use memoryx.api.plugin", DeprecationWarning, stacklevel=2)
from memoryx.api.plugin import register  # noqa: E402
__all__ = ["register"]
