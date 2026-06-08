"""DEPRECATED — moved to memoryx.runtime.event_bus."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.event_bus is deprecated; use memoryx.runtime.event_bus", DeprecationWarning, stacklevel=2)
from memoryx.runtime.event_bus import EventBus
__all__ = ["EventBus"]
