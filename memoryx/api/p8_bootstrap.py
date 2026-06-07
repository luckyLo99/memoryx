"""DEPRECATED — renamed to memoryx.api.bootstrap."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.api.p8_bootstrap is deprecated; use memoryx.api.bootstrap", DeprecationWarning, stacklevel=2)
from memoryx.api.bootstrap import install_p8_observability as install_p8_observability
__all__ = ["install_p8_observability"]
