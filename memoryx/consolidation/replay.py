"""Memory consolidation: hippocampal replay, reconsolidation, and background scheduling.

Implements:
- ReplayBuffer: stores recent experiences for offline replay
- HippocampalReplay: simulates hippocampal replay during idle periods
- MemoryReconsolidation: updates memory traces with new related info
- ConsolidationScheduler: background job runner

References:
- McClelland et al. (1995). Complementary learning systems
- Nadel & Moscovitch (1997). Memory consolidation, retrograde amnesia
- Dudai (2004). The neurobiology of consolidations
- Lewis & Durrant (2011). Overlapping memory replay
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ReplayEvent:
    event_id: str = ""
    content: str = ""
    importance: float = 0.5
    memory_type: str = "episodic"
    timestamp: float = 0.0
    session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ReplayBuffer:
    def __init__(self, max_size: int = 1000):
        self.buffer: deque[ReplayEvent] = deque(maxlen=max_size)
        self.max_size = max_size

    def add(self, event: ReplayEvent) -> None:
        self.buffer.append(event)

    def sample(self, n: int = 10, min_importance: float = 0.0) -> list[ReplayEvent]:
        candidates = [e for e in self.buffer if e.importance >= min_importance]
        candidates.sort(key=lambda e: e.importance, reverse=True)
        return candidates[:n]

    def size(self) -> int:
        return len(self.buffer)

    def clear(self) -> None:
        self.buffer.clear()


class HippocampalReplay:
    PLACEHOLDER_REPLAY_INTERVAL = 300

    def __init__(self, buffer: ReplayBuffer, repository: Any = None):
        self.buffer = buffer
        self.repository = repository
        self.replay_count = 0

    async def replay(self, n: int = 10, min_importance: float = 0.3) -> int:
        events = self.buffer.sample(n, min_importance)
        if not events:
            return 0
        replayed = 0
        for event in events:
            if self.repository is not None:
                try:
                    await self.repository.increment_access_count(event.event_id)
                except Exception:
                    pass
            replayed += 1
            self.replay_count += 1
        logger.info("Replayed %d memories (total=%d)", replayed, self.replay_count)
        return replayed


class MemoryReconsolidation:
    def __init__(self, repository: Any = None, conflict_detector: Any = None):
        self.repository = repository
        self.conflict_detector = conflict_detector

    async def reconsolidate(self, memory_id: str, new_content: str,
                           new_importance: float = 0.5) -> dict[str, Any]:
        result = {"memory_id": memory_id, "updated": False, "conflicts": []}
        if self.repository is None:
            return result
        try:
            memory = await self.repository.get_memory(memory_id)
            if memory is None:
                return result
            old_content = memory.get("content", "")
            if old_content != new_content:
                await self.repository.db.execute(
                    "UPDATE memories SET content = ?, importance_score = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (new_content, new_importance, memory_id)
                )
                result["updated"] = True
            if self.conflict_detector:
                conflicts = await self.conflict_detector.detect([memory])
                result["conflicts"] = conflicts
        except Exception as e:
            logger.error("Reconsolidation failed: %s", e)
        return result


class ConsolidationScheduler:
    def __init__(self, repository: Any = None,
                 replay: HippocampalReplay | None = None,
                 consolidation_engine: Any = None,
                 idle_interval: int = 300,
                 max_retries: int = 3):
        self.repository = repository
        self.replay = replay
        self.consolidation_engine = consolidation_engine
        self.idle_interval = idle_interval
        self.max_retries = max_retries
        self._task: asyncio.Task | None = None
        self._running = False
        self._metrics: dict[str, int] = {
            "passes_completed": 0, "passes_failed": 0,
            "total_replayed": 0, "total_decayed": 0,
            "total_reinforced": 0, "total_merged": 0, "total_reviews": 0,
        }
        self._last_pass_time: float = 0.0
        self._last_error: str | None = None

    @property
    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    @property
    def last_pass_time(self) -> float:
        return self._last_pass_time

    @property
    def last_error(self) -> str | None:
        return self._last_error

    async def health(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "task_active": self._task is not None and not self._task.done(),
            "idle_interval": self.idle_interval,
            "passes_completed": self._metrics["passes_completed"],
            "passes_failed": self._metrics["passes_failed"],
            "last_pass_time": self._last_pass_time,
            "last_error": self._last_error,
            "metrics": dict(self._metrics),
        }

    async def _background_loop(self) -> None:
        self._running = True
        while self._running:
            try:
                await asyncio.sleep(self.idle_interval)
                for attempt in range(self.max_retries):
                    try:
                        await self._run_consolidation_pass()
                        self._metrics["passes_completed"] += 1
                        self._last_pass_time = time.time()
                        self._last_error = None
                        break
                    except Exception as e:
                        self._last_error = str(e)
                        if attempt < self.max_retries - 1:
                            wait = 2 ** attempt
                            logger.warning("Consolidation pass attempt %d/%d failed, retrying in %ds: %s",
                                           attempt + 1, self.max_retries, wait, e)
                            await asyncio.sleep(wait)
                        else:
                            self._metrics["passes_failed"] += 1
                            logger.error("Consolidation pass failed after %d attempts: %s", self.max_retries, e)
            except asyncio.CancelledError:
                logger.info("Consolidation scheduler cancelled")
                break
            except Exception as e:
                self._metrics["passes_failed"] += 1
                self._last_error = str(e)
                logger.error("Consolidation background loop error: %s", e)
        self._running = False

    async def _run_consolidation_pass(self) -> dict[str, int]:
        results: dict[str, int] = {}
        if self.replay is not None:
            try:
                replayed = await self.replay.replay(n=5)
                results["replayed"] = replayed
                self._metrics["total_replayed"] += replayed
            except Exception as e:
                logger.warning("Replay pass failed (non-fatal): %s", e)
        if self.consolidation_engine is not None:
            for op_name, op_method in [
                ("decay", "apply_decay"),
                ("reinforce", "reinforce_memories"),
                ("merged", "merge_duplicates"),
                ("reviews", "process_due_reviews"),
            ]:
                try:
                    method = getattr(self.consolidation_engine, op_method, None)
                    if method is None:
                        continue
                    count = await method()
                    results[op_name] = count
                    key = "total_" + op_name
                    if key in self._metrics:
                        self._metrics[key] += count
                except Exception as e:
                    logger.warning("Consolidation %s failed (non-fatal): %s", op_name, e)
        return results

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            logger.warning("Consolidation scheduler already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._background_loop())
        logger.info("Consolidation scheduler started (interval=%ds)", self.idle_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        logger.info("Consolidation scheduler stopped")

    def is_running(self) -> bool:
        return self._running

    async def run_once(self) -> dict[str, int]:
        return await self._run_consolidation_pass()
