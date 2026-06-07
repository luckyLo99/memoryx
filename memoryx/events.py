"""DEPRECATED — moved to memoryx.runtime.events."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.events is deprecated; use memoryx.runtime.events", DeprecationWarning, stacklevel=2)
from memoryx.runtime.events import MemoryEvent, MemoryEventType, EventPriority, EventHandler, MiddlewareHandler
__all__ = ["MemoryEvent", "MemoryEventType", "EventPriority", "EventHandler", "MiddlewareHandler"]
