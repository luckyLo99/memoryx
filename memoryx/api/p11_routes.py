"""DEPRECATED — renamed to memoryx.api.memories."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.api.p11_routes is deprecated; use memoryx.api.memories", DeprecationWarning, stacklevel=2)
from memoryx.api.memories import create_p11_router as create_p11_router  # noqa: E402
__all__ = ["create_p11_router"]
