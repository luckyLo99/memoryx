"""DEPRECATED - use memoryx.hooks.HermesCompatibilityAdapter directly."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.hermes_adapter is deprecated; use memoryx.hooks.HermesCompatibilityAdapter", DeprecationWarning, stacklevel=2)
from memoryx.hooks import HermesCompatibilityAdapter  # noqa: E402
__all__ = ["HermesCompatibilityAdapter"]
