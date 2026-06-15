"""EvolutionManager: orchestrates preference signal detection and trajectory appending."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from .models import (
    EvolutionDecision,
    EvolutionNode,
    EvolutionTrajectory,
    PreferenceSignal,
    PreferenceSignalDetector,
)
from .repository import EvolutionRepository

_logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"evo_{uuid.uuid4().hex[:12]}"


class EvolutionManager:
    """High-level manager that decides ADD vs EVOLVE vs CONFLICT for new memory content."""

    def __init__(self, repository: EvolutionRepository) -> None:
        self.repository = repository
        self.detector = PreferenceSignalDetector()
        # Modules that are pure "false contradiction" are routed to conflict_resolver
        # by the caller. Evolution only handles non-conflicting preferences/opinions/facts.

    def observe(
        self,
        content: str,
        entity_id: str = "user",
        memory_id: Optional[str] = None,
    ) -> list[EvolutionNode]:
        """Detect signals in content and append nodes to the trajectory.

        Returns the list of new (or refreshed) EvolutionNodes that were written.
        """
        signals = self.detector.detect(content, entity_id=entity_id, memory_id=memory_id)
        written: list[EvolutionNode] = []
        for sig in signals:
            node = self._append_signal(sig)
            if node is not None:
                written.append(node)
        return written

    def upsert_node(self, signal: PreferenceSignal) -> EvolutionNode:
        """Public method to append a single signal as a new trajectory node."""
        return self._append_signal(signal)

    def _append_signal(self, signal: PreferenceSignal) -> Optional[EvolutionNode]:
        if not signal.is_change:
            return None
        now = _utcnow()
        latest = self.repository.get_active(signal.entity_id, signal.slot)
        # Skip duplicate (same value as latest)
        if latest is not None and latest.value.strip() == signal.value.strip():
            return None
        new_node = EvolutionNode(
            id=_new_id(),
            entity_id=signal.entity_id,
            slot=signal.slot,
            value=signal.value,
            kind=signal.kind,
            valid_from=now,
            valid_to=None,
            confidence=signal.confidence,
            source_memory_id=signal.source_memory_id,
            context=signal.context[:500],
            created_at=now,
            active_state="active",
        )
        return self.repository.upsert_node(new_node)

    def get_trajectory(self, entity_id: str, slot: str) -> EvolutionTrajectory:
        nodes = self.repository.list_by_entity_slot(entity_id, slot, include_inactive=True)
        return EvolutionTrajectory(entity_id=entity_id, slot=slot, nodes=nodes)

    def list_slots(self, entity_id: str) -> list[str]:
        return self.repository.list_slots(entity_id)

    def get_latest(self, entity_id: str, slot: str) -> Optional[EvolutionNode]:
        return self.repository.get_active(entity_id, slot)

    def decide(self, signal: PreferenceSignal) -> EvolutionDecision:
        """Classify a new signal as ADD / EVOLVE / CONFLICT.

        EVOLVE: signal refers to an existing slot and differs from latest value.
        ADD: no existing trajectory for (entity, slot).
        CONFLICT: caller has separately determined the new value is a real fact-contradiction.
        """
        latest = self.repository.get_active(signal.entity_id, signal.slot)
        if latest is None:
            return EvolutionDecision.ADD
        if latest.value.strip() == signal.value.strip():
            return EvolutionDecision.ADD  # duplicate, no-op
        return EvolutionDecision.EVOLVE

    def apply_ebbinghaus_decay(self, entity_id: str = "user", half_life_hours: float = 24 * 30) -> int:
        """Decay scores for all active nodes using Ebbinghaus R = e^(-t/S).

        Returns count of nodes updated.
        """
        import math
        now = datetime.now(timezone.utc)
        updated = 0
        for slot in self.repository.list_slots(entity_id):
            nodes = self.repository.list_by_entity_slot(entity_id, slot, include_inactive=True)
            for n in nodes:
                try:
                    vf = datetime.fromisoformat(n.valid_from.replace("Z", "+00:00"))
                except Exception:
                    _logger.warning("Skipping evolution node %s with invalid valid_from: %s", n.id, n.valid_from)
                    continue
                if vf.tzinfo is None:
                    vf = vf.replace(tzinfo=timezone.utc)
                hours = max(0.0, (now - vf).total_seconds() / 3600.0)
                retention = math.exp(-hours / max(0.001, half_life_hours))
                self.repository.update_decay(n.id, 1.0 - retention)
                updated += 1
        return updated
