"""DEPRECATED — imports now available directly from memoryx.hooks."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.manager is deprecated; import directly from memoryx.hooks", DeprecationWarning, stacklevel=2)
from memoryx.hooks import DeadLetterQueue, EventDispatcher, HealthMonitor, MemoryHookManager, QueueManager, RetryManager, SessionEventListener, SubscriberManager
__all__ = ["DeadLetterQueue", "EventDispatcher", "HealthMonitor", "MemoryHookManager", "QueueManager", "RetryManager", "SessionEventListener", "SubscriberManager"]
