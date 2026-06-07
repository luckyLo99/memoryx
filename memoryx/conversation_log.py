"""DEPRECATED — moved to memoryx.storage.conversation_log."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.conversation_log is deprecated; use memoryx.storage.conversation_log", DeprecationWarning, stacklevel=2)
from memoryx.storage.conversation_log import ConversationLogStore
__all__ = ["ConversationLogStore"]
