"""Attention Focus System — cognitive主线追踪与打断恢复.

Based on:
- Cognitive psychology: "Focus of Attention" (Cowan 2001)
- Transformer attention: query-key-value gating for relevance scoring
- Task-switching research: context stacks for interruption recovery (Trafton et al. 2003)

Core concept:
- Primary task maintains dominant activation (like a spotlight)
- Interruptions push current context onto a stack
- Return-to-mainline detected via intent classification
- Context restored from stack, attention refocused
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from memoryx.temporal.time_provider import TimeProvider, get_time_provider

logger = logging.getLogger(__name__)

# Activation decay: how fast a task fades when not active
# Half-life in seconds. 300s = 5 minutes to decay by 50%
_ACTIVATION_HALF_LIFE: float = 300.0

# Minimum activation to be considered "active"
_MIN_ACTIVATION: float = 0.1

# Threshold to detect "return to mainline" intent
_RETURN_CONFIDENCE_THRESHOLD: float = 0.6


@dataclass
class AttentionFrame:
    """A single frame of attention — one task context."""

    task_id: str
    task_description: str
    reasoning_chain: list[str] = field(default_factory=list)
    active_todos: list[str] = field(default_factory=list)
    activation: float = 1.0  # 0.0–1.0, dominant = highest
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Stack for nested interruptions
    parent_task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InterruptionRecord:
    """Record of an interruption event."""

    interrupted_task_id: str
    interrupting_query: str
    timestamp: datetime
    recovered_at: datetime | None = None
    recovery_successful: bool = False


class AttentionFocusEngine:
    """Manages agent attention across tasks and interruptions.

    Key behaviors:
    1. Track dominant task with activation-based decay
    2. Save full context on interruption
    3. Detect return-to-mainline from user queries
    4. Restore context and reasoning chain on return
    """

    def __init__(
        self,
        *,
        repository=None,
        time_provider: TimeProvider | None = None,
        half_life_seconds: float = _ACTIVATION_HALF_LIFE,
    ) -> None:
        self.repository = repository
        self.time_provider = time_provider or get_time_provider()
        self.half_life = half_life_seconds
        self._frames: dict[str, AttentionFrame] = {}
        self._dominant_task_id: str | None = None
        self._interruption_stack: list[AttentionFrame] = []
        self._interruption_history: list[InterruptionRecord] = []
        self._interruption_history_maxlen: int = 1000
        self._lock = asyncio.Lock()

    # ── Core API ──────────────────────────────────────────────────

    async def register_task(
        self,
        *,
        task_id: str,
        description: str,
        reasoning_chain: list[str] | None = None,
        todos: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AttentionFrame:
        """Register a new task as the current focus."""
        async with self._lock:
            # If there was a previous dominant task, push to stack
            if self._dominant_task_id and self._dominant_task_id != task_id:
                old_frame = self._frames.get(self._dominant_task_id)
                if old_frame:
                    self._interruption_stack.append(old_frame)
                    logger.debug("Pushed task %s to interruption stack", old_frame.task_id)

            now = self.time_provider.now()
            frame = AttentionFrame(
                task_id=task_id,
                task_description=description,
                reasoning_chain=list(reasoning_chain) if reasoning_chain else [],
                active_todos=list(todos) if todos else [],
                activation=1.0,
                created_at=now,
                last_accessed_at=now,
                parent_task_id=self._dominant_task_id,
                metadata=dict(metadata) if metadata else {},
            )
            self._frames[task_id] = frame
            self._dominant_task_id = task_id
            await self._persist_frame(frame)
            return frame

    async def on_user_message(self, session_id: str, content: str) -> dict[str, Any]:
        """Process incoming user message for attention management.

        Returns:
            {
                "action": "continue" | "interrupted" | "returned",
                "dominant_task": current dominant task info,
                "restored_context": context to inject if returned,
                "attention_snapshot": current attention state,
            }
        """
        async with self._lock:
            # 1. Decay all activations
            self._decay_all()

            # 2. Classify intent
            intent = self._classify_intent(content)

            # 3. Handle based on intent
            if intent == "return_to_mainline":
                return await self._handle_return(session_id, content)
            elif intent == "interruption":
                return await self._handle_interruption(session_id, content)
            else:
                # Continue current task
                return await self._handle_continue(session_id, content)

    async def get_attention_snapshot(self) -> dict[str, Any]:
        """Return current attention state for debugging/context."""
        async with self._lock:
            return self._get_attention_snapshot_unlocked()

    def _get_attention_snapshot_unlocked(self) -> dict[str, Any]:
        """Internal: return attention snapshot without acquiring lock (caller must hold lock)."""
        self._decay_all()
        return {
            "dominant_task": self._dominant_task_id,
            "dominant_description": (
                self._frames[self._dominant_task_id].task_description
                if self._dominant_task_id and self._dominant_task_id in self._frames
                else None
            ),
            "active_frames": len([f for f in self._frames.values() if f.activation > _MIN_ACTIVATION]),
            "stack_depth": len(self._interruption_stack),
            "frames": [
                {
                    "task_id": f.task_id,
                    "description": f.task_description[:60],
                    "activation": round(f.activation, 3),
                }
                for f in sorted(self._frames.values(), key=lambda x: x.activation, reverse=True)
                if f.activation > _MIN_ACTIVATION
            ],
        }

    async def pop_stack(self) -> AttentionFrame | None:
        """Manually pop the interruption stack. Used when user says 'go back'."""
        async with self._lock:
            return await self._pop_stack_unlocked()

    async def _pop_stack_unlocked(self) -> AttentionFrame | None:
        """Internal: pop stack without acquiring lock (caller must hold lock)."""
        if not self._interruption_stack:
            return None
        frame = self._interruption_stack.pop()
        self._dominant_task_id = frame.task_id
        frame.activation = 1.0
        frame.last_accessed_at = self.time_provider.now()
        self._frames[frame.task_id] = frame
        await self._persist_frame(frame)
        return frame

    # ── Intent Classification ─────────────────────────────────────

    def _classify_intent(self, content: str) -> str:
        """Classify user message intent regarding attention.

        Returns: "continue" | "interruption" | "return_to_mainline"
        """
        lower = content.lower()

        # Return-to-mainline signals
        return_patterns = [
            "back to ", "return to ", "回到", "继续说", "刚才的",
            "where were we", "what were we", "resume", "continue with ",
            "go back to ", "let's get back", "anyway", "regardless",
        ]
        for pattern in return_patterns:
            if pattern in lower:
                return "return_to_mainline"

        # Interruption signals — completely new topic
        interruption_patterns = [
            "by the way", "顺便", "对了", "oh and", "one more thing",
            "different topic", "换个话题", "问个别的",
        ]
        for pattern in interruption_patterns:
            if pattern in lower:
                return "interruption"

        # If no dominant task yet, treat as new task (interruption from null)
        if self._dominant_task_id is None:
            return "interruption"

        # Check if content is related to dominant task
        dominant = self._frames.get(self._dominant_task_id)
        if dominant:
            relevance = self._compute_relevance(content, dominant)
            if relevance < 0.3:
                return "interruption"

        return "continue"

    def _compute_relevance(self, query: str, frame: AttentionFrame) -> float:
        """Compute relevance score between query and task frame (0.0–1.0).

        Simple keyword overlap. Production could use embedding similarity.
        """
        query_words = set(query.lower().split())
        task_words = set(frame.task_description.lower().split())
        for r in frame.reasoning_chain:
            task_words.update(r.lower().split())
        for t in frame.active_todos:
            task_words.update(t.lower().split())

        if not query_words or not task_words:
            return 0.0

        overlap = len(query_words & task_words)
        # Jaccard-like similarity
        union = len(query_words | task_words)
        return overlap / union if union > 0 else 0.0

    # ── Handlers ──────────────────────────────────────────────────

    async def _handle_return(self, session_id: str, content: str) -> dict[str, Any]:
        """User wants to return to previous mainline task."""
        # Pop from stack (already inside lock via on_user_message)
        restored_frame = await self._pop_stack_unlocked()

        if restored_frame is None:
            # No stack, try to recover most active historical frame
            restored_frame = self._recover_most_active_frame()

        if restored_frame is None:
            return {
                "action": "returned",
                "success": False,
                "reason": "no_previous_task",
                "restored_context": None,
                "attention_snapshot": self._get_attention_snapshot_unlocked(),
            }

        # Record successful recovery
        if self._interruption_history:
            last = self._interruption_history[-1]
            if last.recovered_at is None:
                last.recovered_at = self.time_provider.now()
                last.recovery_successful = True

        context = {
            "task_id": restored_frame.task_id,
            "task_description": restored_frame.task_description,
            "reasoning_chain": restored_frame.reasoning_chain,
            "active_todos": restored_frame.active_todos,
            "message": f"Restored focus to: {restored_frame.task_description}",
        }

        return {
            "action": "returned",
            "success": True,
            "restored_context": context,
            "attention_snapshot": self._get_attention_snapshot_unlocked(),
        }

    async def _handle_interruption(self, session_id: str, content: str) -> dict[str, Any]:
        """User interrupted with a new topic. Save current context."""
        old_dominant = self._dominant_task_id

        # Create a new frame for the interruption (uuid4 suffix prevents task_id collision)
        new_task_id = f"interrupt_{session_id}_{self.time_provider.now().timestamp()}_{uuid.uuid4().hex[:8]}"
        frame = AttentionFrame(
            task_id=new_task_id,
            task_description=content[:200],
            activation=1.0,
            created_at=self.time_provider.now(),
            last_accessed_at=self.time_provider.now(),
            parent_task_id=old_dominant,
        )
        self._frames[new_task_id] = frame
        self._dominant_task_id = new_task_id

        # Record interruption
        if old_dominant:
            self._interruption_history.append(InterruptionRecord(
                interrupted_task_id=old_dominant,
                interrupting_query=content[:500],
                timestamp=self.time_provider.now(),
            ))
            # Cap history to prevent unbounded growth
            if len(self._interruption_history) > self._interruption_history_maxlen:
                self._interruption_history = self._interruption_history[-self._interruption_history_maxlen:]

        await self._persist_frame(frame)

        return {
            "action": "interrupted",
            "previous_task": old_dominant,
            "new_task": new_task_id,
            "attention_snapshot": self._get_attention_snapshot_unlocked(),
        }

    async def _handle_continue(self, session_id: str, content: str) -> dict[str, Any]:
        """Continue current task — boost activation."""
        if self._dominant_task_id and self._dominant_task_id in self._frames:
            frame = self._frames[self._dominant_task_id]
            frame.activation = min(1.0, frame.activation + 0.2)
            frame.last_accessed_at = self.time_provider.now()
            await self._persist_frame(frame)

        return {
            "action": "continue",
            "attention_snapshot": self._get_attention_snapshot_unlocked(),
        }

    # ── Decay & Recovery ──────────────────────────────────────────

    def _decay_all(self) -> None:
        """Apply exponential decay to all frame activations."""
        now = self.time_provider.now()
        for frame in list(self._frames.values()):
            elapsed = (now - frame.last_accessed_at).total_seconds()
            # Exponential decay: A = A0 * (0.5)^(t / half_life)
            decay_factor = 0.5 ** (elapsed / self.half_life)
            frame.activation *= decay_factor
            frame.last_accessed_at = now

            if frame.activation < _MIN_ACTIVATION:
                self._frames.pop(frame.task_id, None)

    def _recover_most_active_frame(self) -> AttentionFrame | None:
        """Find the most active frame from history."""
        if not self._frames:
            return None
        best = max(self._frames.values(), key=lambda f: f.activation)
        if best.activation < _MIN_ACTIVATION:
            return None
        return best

    # ── Persistence ───────────────────────────────────────────────

    async def _persist_frame(self, frame: AttentionFrame) -> None:
        if self.repository is None:
            return
        try:
            await self.repository.db.execute(
                "INSERT INTO attention_frames(task_id, task_description, reasoning_chain, "
                "active_todos, activation, created_at, last_accessed_at, parent_task_id, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET "
                "task_description=excluded.task_description, reasoning_chain=excluded.reasoning_chain, "
                "active_todos=excluded.active_todos, activation=excluded.activation, "
                "last_accessed_at=excluded.last_accessed_at, parent_task_id=excluded.parent_task_id, "
                "metadata=excluded.metadata;",
                (
                    frame.task_id,
                    frame.task_description,
                    json.dumps(frame.reasoning_chain),
                    json.dumps(frame.active_todos),
                    frame.activation,
                    frame.created_at.isoformat(),
                    frame.last_accessed_at.isoformat(),
                    frame.parent_task_id,
                    json.dumps(frame.metadata),
                ),
            )
        except Exception:
            logger.exception("Failed to persist attention frame %s", frame.task_id)
