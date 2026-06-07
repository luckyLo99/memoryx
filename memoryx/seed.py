"""DEPRECATED — moved to memoryx.storage.seed."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.seed is deprecated; use memoryx.storage.seed", DeprecationWarning, stacklevel=2)
from memoryx.storage.seed import ConversationSeed
__all__ = ["ConversationSeed"]
