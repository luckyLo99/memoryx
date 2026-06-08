"""DEPRECATED - moved to memoryx.temporal.scorer."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.temporal_scorer is deprecated; use memoryx.temporal.scorer", DeprecationWarning, stacklevel=2)
from memoryx.temporal.scorer import TemporalScorer, TemporalQueryIntent
__all__ = ["TemporalScorer", "TemporalQueryIntent"]
