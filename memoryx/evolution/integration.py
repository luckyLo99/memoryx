"""Integration layer: ConflictResolver <-> EvolutionManager coordination.

When a new memory is being added, the integration layer first checks whether
it's a candidate for evolutionary append (e.g. "favorite singer: 张杰" then
"favorite singer: 房东的猫"). If yes, it routes to EvolutionManager and skips
the conflict alarm. Otherwise, falls through to the existing conflict resolver.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .manager import EvolutionManager
from .models import EvolutionDecision, EvolutionNode, PreferenceSignal

_logger = logging.getLogger(__name__)


@dataclass
class IntegrationDecision:
    """Result of the integration-layer routing."""

    is_evolution: bool
    node: Optional[EvolutionNode] = None
    decision: EvolutionDecision = EvolutionDecision.ADD
    reason: str = ""


class EvolutionIntegration:
    """Coordinates EvolutionManager with the rest of the memory pipeline.

    Designed to be called from extractors / writers when a new memory is
    about to be persisted. Backward-compatible: if no evolution manager is
    wired, behaves as a no-op pass-through.
    """

    def __init__(self, manager: Optional[EvolutionManager] = None) -> None:
        self.manager = manager

    def observe_content(
        self,
        content: str,
        entity_id: str = "user",
        memory_id: Optional[str] = None,
    ) -> list[EvolutionNode]:
        """Convenience: detect signals and append to trajectory.

        Returns list of nodes written.
        """
        if self.manager is None:
            return []
        return self.manager.observe(content, entity_id=entity_id, memory_id=memory_id)

    def route(
        self,
        signal: PreferenceSignal,
    ) -> IntegrationDecision:
        """Decide whether a preference signal is an evolution event.

        Returns IntegrationDecision; callers (e.g. ConflictResolver wrappers)
        use it to skip conflict alarms.
        """
        if self.manager is None:
            return IntegrationDecision(is_evolution=False, reason="no_manager")
        decision = self.manager.decide(signal)
        if decision == EvolutionDecision.CONFLICT:
            return IntegrationDecision(
                is_evolution=False, decision=EvolutionDecision.CONFLICT, reason="conflict"
            )
        if decision == EvolutionDecision.ADD:
            # brand-new slot → still write to evolution
            node = self.manager.upsert_node(signal)
            return IntegrationDecision(
                is_evolution=True, node=node, decision=EvolutionDecision.ADD, reason="new_slot"
            )
        # EVOLVE: append new node
        node = self.manager.upsert_node(signal)
        return IntegrationDecision(
            is_evolution=True, node=node, decision=EvolutionDecision.EVOLVE, reason="appended"
        )

    def is_preference_change(self, content: str) -> bool:
        """Quick check: does the text look like a preference change?"""
        if self.manager is None:
            return False
        signals = self.manager.detector.detect(content)
        return any(s.is_change for s in signals)
