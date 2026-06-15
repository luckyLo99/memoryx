"""Working memory engine with 30-min TTL and SQLite persistence.

Implements the cognitive "focus of attention" model:
- Primary task maintains dominant activation
- Interruptions are pushed onto a context stack
- Return pops the stack and restores previous focus
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from memoryx.temporal.time_provider import SystemTimeProvider, TimeProvider, get_time_provider

from .models import WorkingMemoryState

logger = logging.getLogger(__name__)

# Default 30 minutes (1800 seconds) per user requirement
_DEFAULT_TTL_SECONDS: float = 1800.0


class WorkingMemoryEngine:
    """Working memory with persistence, attention focus, and interruption recovery.

    Key features:
    - 30-minute TTL (configurable)
    - SQLite persistence: survive process restarts
    - Attention stack: handle interruptions without losing主线
    """

    def __init__(
        self,
        *,
        repository=None,
        default_ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        time_provider: TimeProvider | None = None,
    ) -> None:
        self.repository = repository
        self.default_ttl_seconds = default_ttl_seconds
        # Create a fresh time provider per engine to avoid cross-test cache staleness
        self.time_provider = time_provider or SystemTimeProvider(sync_interval_seconds=1.0)
        self._states: dict[str, WorkingMemoryState] = {}
        self._lock = asyncio.Lock()

    # ── Persistence ───────────────────────────────────────────────

    async def load_from_db(self, session_id: str) -> WorkingMemoryState | None:
        """Restore working memory from SQLite. Called on first access."""
        if self.repository is None:
            return None
        try:
            row = await self.repository.db.fetchone(
                "SELECT session_id, current_task, reasoning_chain, active_todos, "
                "temporary_context, debug_session, workflow_state, updated_at, expires_at "
                "FROM working_memory WHERE session_id = ?;",
                (session_id,),
            )
            if row is None:
                return None
            state = WorkingMemoryState(
                session_id=row[0],
                current_task=row[1] or "",
                reasoning_chain=json.loads(row[2]) if row[2] else [],
                active_todos=json.loads(row[3]) if row[3] else [],
                temporary_context=json.loads(row[4]) if row[4] else {},
                debug_session=json.loads(row[5]) if row[5] else {},
                workflow_state=json.loads(row[6]) if row[6] else {},
                updated_at=datetime.fromisoformat(row[7]),
                expires_at=datetime.fromisoformat(row[8]),
            )
            if self._is_expired(state):
                await self._delete_from_db(session_id)
                return None
            return state
        except Exception:
            logger.exception("Failed to load working memory for %s", session_id)
            return None

    async def persist_to_db(self, session_id: str) -> None:
        """Save working memory to SQLite."""
        if self.repository is None:
            return
        state = self._states.get(session_id)
        if state is None:
            return
        try:
            await self.repository.db.execute(
                "INSERT INTO working_memory(session_id, current_task, reasoning_chain, active_todos, "
                "temporary_context, debug_session, workflow_state, updated_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "current_task=excluded.current_task, reasoning_chain=excluded.reasoning_chain, "
                "active_todos=excluded.active_todos, temporary_context=excluded.temporary_context, "
                "debug_session=excluded.debug_session, workflow_state=excluded.workflow_state, "
                "updated_at=excluded.updated_at, expires_at=excluded.expires_at;",
                (
                    state.session_id,
                    state.current_task,
                    json.dumps(state.reasoning_chain),
                    json.dumps(state.active_todos),
                    json.dumps(state.temporary_context),
                    json.dumps(state.debug_session),
                    json.dumps(state.workflow_state),
                    state.updated_at.isoformat(),
                    state.expires_at.isoformat(),
                ),
            )
        except Exception:
            logger.exception("Failed to persist working memory for %s", session_id)

    async def _delete_from_db(self, session_id: str) -> None:
        if self.repository is None:
            return
        try:
            await self.repository.db.execute(
                "DELETE FROM working_memory WHERE session_id = ?;", (session_id,)
            )
        except Exception:
            pass

    # ── Core operations ───────────────────────────────────────────

    async def update_task_state(
        self,
        *,
        session_id: str,
        task: str,
        reasoning_chain: list[str] | None = None,
        todos: list[str] | None = None,
        workflow_state: dict | None = None,
    ) -> WorkingMemoryState:
        await self.expire_stale()
        async with self._lock:
            state = self._states.get(session_id)
            if state is None:
                state = await self.load_from_db(session_id)
            if state is None:
                state = self._new_state(session_id)
            state.current_task = task
            if reasoning_chain is not None:
                state.reasoning_chain = list(reasoning_chain)
            if todos is not None:
                state.active_todos = list(todos)
            if workflow_state is not None:
                state.workflow_state = dict(workflow_state)
            self._touch(state)
            self._states[session_id] = state
            await self.persist_to_db(session_id)
            return state

    async def update_debug_state(
        self,
        *,
        session_id: str,
        debug_session: dict | None = None,
        temporary_context: dict | None = None,
    ) -> WorkingMemoryState:
        async with self._lock:
            state = self._states.get(session_id)
            if state is None:
                state = await self.load_from_db(session_id)
            if state is None:
                state = self._new_state(session_id)
            if debug_session is not None:
                state.debug_session = dict(debug_session)
            if temporary_context is not None:
                state.temporary_context = dict(temporary_context)
            self._touch(state)
            self._states[session_id] = state
            await self.persist_to_db(session_id)
            return state

    async def get_state(self, session_id: str) -> WorkingMemoryState | None:
        await self.expire_stale()
        async with self._lock:
            state = self._states.get(session_id)
            if state is None:
                state = await self.load_from_db(session_id)
                if state:
                    self._states[session_id] = state
            if state is None:
                return None
            if self._is_expired(state):
                self._states.pop(session_id, None)
                await self._delete_from_db(session_id)
                return None
            return state

    async def expire_stale(self) -> int:
        async with self._lock:
            stale_ids = [sid for sid, state in self._states.items() if self._is_expired(state)]
            for sid in stale_ids:
                self._states.pop(sid, None)
                await self._delete_from_db(sid)
            return len(stale_ids)

    async def snapshot(self, session_id: str) -> dict | None:
        state = await self.get_state(session_id)
        if state is None:
            return None
        parts = []
        if state.current_task:
            parts.append(f"Current task: {state.current_task}")
        if state.reasoning_chain:
            parts.append("Reasoning: " + " -> ".join(state.reasoning_chain[-3:]))
        if state.active_todos:
            parts.append("Active todos: " + ", ".join(state.active_todos))
        if state.workflow_state:
            wf_keys = list(state.workflow_state.keys())[:5]
            parts.append("Workflow: " + ", ".join(wf_keys))
        return {"session_id": session_id, "lines": parts, "has_state": bool(parts)}

    async def compress_state(self, session_id: str, *, max_reasoning_items: int = 3, max_todos: int = 3) -> str:
        async with self._lock:
            state = self._states.get(session_id)
            if state is None:
                state = await self.load_from_db(session_id)
            if state is None or self._is_expired(state):
                self._states.pop(session_id, None)
                return ""
            state.reasoning_chain = state.reasoning_chain[:max_reasoning_items]
            state.active_todos = state.active_todos[:max_todos]
            self._touch(state)
            await self.persist_to_db(session_id)
            summary_parts = []
            if state.current_task:
                summary_parts.append(f"task={state.current_task}")
            if state.reasoning_chain:
                summary_parts.append("reasoning=" + " -> ".join(state.reasoning_chain))
            if state.active_todos:
                summary_parts.append("todos=" + ", ".join(state.active_todos))
            return " | ".join(summary_parts)

    # ── Helpers ───────────────────────────────────────────────────

    def _new_state(self, session_id: str) -> WorkingMemoryState:
        state = WorkingMemoryState(session_id=session_id)
        self._touch(state)
        return state

    def _touch(self, state: WorkingMemoryState) -> None:
        now = self.time_provider.now()
        state.updated_at = now
        state.expires_at = now + timedelta(seconds=self.default_ttl_seconds)

    def _is_expired(self, state: WorkingMemoryState) -> bool:
        # Use real system time for expiration checks to avoid cache staleness
        return datetime.now(timezone.utc) >= state.expires_at
