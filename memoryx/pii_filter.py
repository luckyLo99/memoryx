"""DEPRECATED — moved to memoryx.safety.pii_filter."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.pii_filter is deprecated; use memoryx.safety.pii_filter", DeprecationWarning, stacklevel=2)
from memoryx.safety.pii_filter import PIIFilter, PIISpan, PIIResult  # noqa: E402
__all__ = ["PIIFilter", "PIISpan", "PIIResult"]
