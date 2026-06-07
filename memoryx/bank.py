"""DEPRECATED — moved to memoryx.storage.bank."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.bank is deprecated; use memoryx.storage.bank", DeprecationWarning, stacklevel=2)
from memoryx.storage.bank import MemoryBank
__all__ = ["MemoryBank"]
