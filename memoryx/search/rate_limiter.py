from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(slots=True)
class RateLimiterState:
    current_limit: int
    min_limit: int
    max_limit: int
    last_rate_limit_at: float = 0.0
    last_timeout_at: float = 0.0
    success_count: int = 0


class AdaptiveConcurrencyLimiter:
    """Provider-aware adaptive concurrency limiter.

    Rules:
    - 429 / rate limit -> decrease quickly
    - timeout -> decrease mildly
    - stable success window -> increase slowly
    """

    def __init__(
        self,
        *,
        initial: int = 6,
        min_limit: int = 2,
        max_limit: int = 8,
        success_window: int = 20,
    ) -> None:
        self.state = RateLimiterState(
            current_limit=initial,
            min_limit=min_limit,
            max_limit=max_limit,
        )
        self.success_window = success_window
        self._lock = asyncio.Lock()

    async def limit(self) -> asyncio.Semaphore:
        async with self._lock:
            return asyncio.Semaphore(self.state.current_limit)

    async def on_success(self) -> None:
        async with self._lock:
            self.state.success_count += 1
            if (
                self.state.success_count >= self.success_window
                and self.state.current_limit < self.state.max_limit
            ):
                self.state.current_limit += 1
                self.state.success_count = 0

    async def on_rate_limit(self) -> None:
        async with self._lock:
            self.state.last_rate_limit_at = time.time()
            self.state.success_count = 0
            self.state.current_limit = max(
                self.state.min_limit,
                self.state.current_limit // 2,
            )

    async def on_timeout(self) -> None:
        async with self._lock:
            self.state.last_timeout_at = time.time()
            self.state.success_count = 0
            self.state.current_limit = max(
                self.state.min_limit,
                self.state.current_limit - 1,
            )

    async def snapshot(self) -> dict:
        async with self._lock:
            return {
                "current_limit": self.state.current_limit,
                "min_limit": self.state.min_limit,
                "max_limit": self.state.max_limit,
                "success_count": self.state.success_count,
                "last_rate_limit_at": self.state.last_rate_limit_at,
                "last_timeout_at": self.state.last_timeout_at,
            }