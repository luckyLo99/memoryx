"""Unified time source for MemoryX.

Provides a single internal clock that all modules read from, rather than
each module calling datetime.now() independently. Like a wristwatch:
- Internal time advances smoothly between syncs
- Occasional calibration against system time
- Supports time-travel for testing long-term memory behaviors

Usage (production):
    from memoryx.temporal.time_provider import get_time_provider
    tp = get_time_provider()
    now = tp.now()

Usage (testing - time travel):
    from memoryx.temporal.time_provider import FixedTimeProvider
    tp = FixedTimeProvider()
    tp.advance(days=30)  # jump forward 30 days
    scorer = TemporalScorer(time_provider=tp)
"""
from __future__ import annotations

import time as _time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import ClassVar


class TimeProvider(ABC):
    """Abstract time source. All time-dependent modules should read from here."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current time as an offset-aware datetime (UTC)."""
        ...

    @abstractmethod
    def time(self) -> float:
        """Return the current time as a Unix timestamp (seconds since epoch)."""
        ...


@dataclass
class SystemTimeProvider(TimeProvider):
    """Production time provider. Caches time and syncs periodically.

    Reduces system calls from O(N) per operation to O(1) between syncs.
    """

    sync_interval_seconds: float = 60.0
    _last_sync_monotonic: float = field(default=0.0, repr=False)
    _cached_dt: datetime | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._cached_dt is None:
            self._cached_dt = datetime.now(timezone.utc)
            self._last_sync_monotonic = _time.monotonic()

    def now(self) -> datetime:
        t = _time.monotonic()
        if t - self._last_sync_monotonic > self.sync_interval_seconds:
            self._cached_dt = datetime.now(timezone.utc)
            self._last_sync_monotonic = t
        # Defensive: _cached_dt should never be None after __post_init__
        assert self._cached_dt is not None
        return self._cached_dt

    def time(self) -> float:
        return self.now().timestamp()

    def force_sync(self) -> None:
        """Immediately recalibrate against system time."""
        self._cached_dt = datetime.now(timezone.utc)
        self._last_sync_monotonic = _time.monotonic()


@dataclass
class FixedTimeProvider(TimeProvider):
    """Deterministic time provider for tests and simulations.

    Allows "time travel" so tests can verify long-term behaviors like
    Ebbinghaus forgetting curves without waiting days.
    """

    _fixed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def now(self) -> datetime:
        return self._fixed

    def time(self) -> float:
        return self._fixed.timestamp()

    def advance(self, **kwargs: float | int) -> None:
        """Jump forward by timedelta kwargs, e.g. advance(days=3, hours=12)."""
        self._fixed += timedelta(**kwargs)  # type: ignore[arg-type]

    def rewind(self, **kwargs: float | int) -> None:
        """Jump backward by timedelta kwargs."""
        self._fixed -= timedelta(**kwargs)  # type: ignore[arg-type]

    def set_to(self, dt: datetime) -> None:
        """Set the fixed time to an explicit datetime."""
        self._fixed = dt


# ── Global default instance ──────────────────────────────────────

_default_provider: TimeProvider | None = None


def get_time_provider() -> TimeProvider:
    """Return the global default time provider (lazy-initialized)."""
    global _default_provider
    if _default_provider is None:
        _default_provider = SystemTimeProvider()
    return _default_provider


def set_time_provider(provider: TimeProvider | None) -> None:
    """Replace the global default provider. Pass None to reset."""
    global _default_provider
    _default_provider = provider
