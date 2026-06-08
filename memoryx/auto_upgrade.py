"""DEPRECATED - moved to memoryx.storage.upgrade_check."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.auto_upgrade is deprecated; use memoryx.storage.upgrade_check.check_update", DeprecationWarning, stacklevel=2)
from memoryx.storage.upgrade_check import check_update
__all__ = ["check_update"]
