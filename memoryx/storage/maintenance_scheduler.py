"""Periodic database maintenance scheduler.

Cleans up:
- Expired working_memory rows (TTL > 30 min)
- Low-activation attention_frames (activation < 0.1)
- Old memory_access_logs (> 90 days)
- Old audit_logs (> 180 days)
- Old memory_versions (keep last 10 per memory)
- Old conversation_logs (> 365 days)
- Old archived_memories (> 730 days)
- Runs VACUUM and WAL checkpoint weekly

Runs on a configurable interval (default: 1 hour).
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .maintenance import StorageMaintenance

if TYPE_CHECKING:
    from .sqlite_async import AsyncSQLite

logger = logging.getLogger(__name__)

# Default maintenance interval in seconds (1 hour)
_DEFAULT_INTERVAL_SECONDS: float = 3600.0

# VACUUM interval in seconds (1 week)
_VACUUM_INTERVAL_SECONDS: float = 7 * 24 * 3600.0


class MaintenanceScheduler:
    """Periodic database maintenance scheduler.

    Runs cleanup tasks on a configurable interval. Start/stop lifecycle
    is managed via asyncio. All errors are caught and logged so the
    scheduler never crashes the system.
    """

    def __init__(
        self,
        db: AsyncSQLite,
        *,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
        vacuum_interval_seconds: float = _VACUUM_INTERVAL_SECONDS,
    ) -> None:
        self._db = db
        self._interval = interval_seconds
        self._vacuum_interval = vacuum_interval_seconds
        self._maintenance = StorageMaintenance()
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_vacuum: float = 0.0

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Start the maintenance scheduler (non-blocking)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._run_loop())
        logger.info("MaintenanceScheduler started (interval=%.0fs)", self._interval)

    def stop(self) -> None:
        """Stop the maintenance scheduler."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.info("MaintenanceScheduler stopped")

    async def _run_loop(self) -> None:
        """Main loop: sleep, then run maintenance, repeat."""
        while self._running:
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                return
            await self.run_maintenance()

    # ── Public entry point for one-shot runs ─────────────────────

    async def run_maintenance(self) -> dict[str, int]:
        """Execute all cleanup tasks once. Returns deletion counts."""
        results: dict[str, int] = {}
        results["expired_working_memory"] = await self._cleanup_expired_working_memory()
        results["low_activation_frames"] = await self._cleanup_low_activation_frames()
        results["old_access_logs"] = await self._cleanup_old_access_logs()
        results["old_audit_logs"] = await self._cleanup_old_audit_logs()
        results["old_memory_versions"] = await self._cleanup_old_memory_versions()
        results["old_conversation_logs"] = await self._cleanup_old_conversation_logs()
        results["old_archived_memories"] = await self._cleanup_old_archived_memories()

        # Weekly VACUUM + WAL checkpoint
        import time as _time
        now = _time.monotonic()
        if now - self._last_vacuum >= self._vacuum_interval:
            await self._run_vacuum()
            self._last_vacuum = now

        total = sum(results.values())
        logger.info("Maintenance run completed: %s (total=%d)", results, total)
        return results

    # ── Cleanup methods ──────────────────────────────────────────

    async def _cleanup_expired_working_memory(self) -> int:
        """DELETE FROM working_memory WHERE expires_at < datetime('now')"""
        try:
            cur = await self._db.execute(
                "DELETE FROM working_memory WHERE expires_at < datetime('now');"
            )
            count = cur or 0
            if count:
                logger.info("Cleaned up %d expired working_memory rows", count)
            return count
        except Exception:
            logger.exception("Failed to cleanup expired working_memory")
            return 0

    async def _cleanup_low_activation_frames(self) -> int:
        """DELETE FROM attention_frames WHERE activation < 0.1"""
        try:
            cur = await self._db.execute(
                "DELETE FROM attention_frames WHERE activation < 0.1;"
            )
            count = cur or 0
            if count:
                logger.info("Cleaned up %d low-activation attention_frames", count)
            return count
        except Exception:
            logger.exception("Failed to cleanup low-activation attention_frames")
            return 0

    async def _cleanup_old_access_logs(self) -> int:
        """DELETE FROM memory_access_logs WHERE created_at < datetime('now', '-90 days')"""
        try:
            cur = await self._db.execute(
                "DELETE FROM memory_access_logs WHERE created_at < datetime('now', '-90 days');"
            )
            count = cur or 0
            if count:
                logger.info("Cleaned up %d old memory_access_logs", count)
            return count
        except Exception:
            logger.exception("Failed to cleanup old memory_access_logs")
            return 0

    async def _cleanup_old_audit_logs(self) -> int:
        """DELETE FROM audit_logs WHERE created_at < datetime('now', '-180 days')"""
        try:
            cur = await self._db.execute(
                "DELETE FROM audit_logs WHERE created_at < datetime('now', '-180 days');"
            )
            count = cur or 0
            if count:
                logger.info("Cleaned up %d old audit_logs", count)
            return count
        except Exception:
            logger.exception("Failed to cleanup old audit_logs")
            return 0

    async def _cleanup_old_memory_versions(self) -> int:
        """Delete old memory_versions keeping only last 10 per memory."""
        try:
            cur = await self._db.execute(
                "DELETE FROM memory_versions WHERE id IN ("
                "  SELECT mv.id FROM memory_versions mv"
                "  WHERE (SELECT COUNT(*) FROM memory_versions mv2"
                "         WHERE mv2.memory_id = mv.memory_id AND mv2.version >= mv.version) > 10"
                ");"
            )
            count = cur or 0
            if count:
                logger.info("Cleaned up %d old memory_versions", count)
            return count
        except Exception:
            logger.exception("Failed to cleanup old memory_versions")
            return 0

    async def _cleanup_old_conversation_logs(self) -> int:
        """DELETE FROM conversation_logs WHERE created_at < datetime('now', '-365 days')"""
        try:
            cur = await self._db.execute(
                "DELETE FROM conversation_logs WHERE created_at < datetime('now', '-365 days');"
            )
            count = cur or 0
            if count:
                logger.info("Cleaned up %d old conversation_logs", count)
            return count
        except Exception:
            logger.exception("Failed to cleanup old conversation_logs")
            return 0

    async def _cleanup_old_archived_memories(self) -> int:
        """DELETE FROM archived_memories WHERE archived_at < datetime('now', '-730 days')"""
        try:
            cur = await self._db.execute(
                "DELETE FROM archived_memories WHERE archived_at < datetime('now', '-730 days');"
            )
            count = cur or 0
            if count:
                logger.info("Cleaned up %d old archived_memories", count)
            return count
        except Exception:
            logger.exception("Failed to cleanup old archived_memories")
            return 0

    async def _run_vacuum(self) -> None:
        """Run VACUUM and WAL checkpoint via StorageMaintenance."""
        try:
            await self._maintenance.compact(self._db)
            logger.info("VACUUM and WAL checkpoint completed")
        except Exception:
            logger.exception("Failed to run VACUUM/WAL checkpoint")
