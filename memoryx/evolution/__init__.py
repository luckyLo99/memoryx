"""MemoryX Evolutionary Trajectory Module.

Tracks how user preferences, opinions, and facts evolve over time without
marking changes as conflicts. For example, "favorite singer: 张杰" at T1
and "favorite singer: 房东的猫" at T2 form one trajectory rather than
a contradiction.
"""
from __future__ import annotations

from .integration import EvolutionIntegration, IntegrationDecision
from .manager import EvolutionManager
from .models import (
    EvolutionDecision,
    EvolutionKind,
    EvolutionNode,
    EvolutionTrajectory,
    PreferenceSignal,
    PreferenceSignalDetector,
)
from .repository import EvolutionRepository, ensure_evolution_table

__all__ = [
    "EvolutionDecision",
    "EvolutionIntegration",
    "EvolutionKind",
    "EvolutionManager",
    "EvolutionNode",
    "EvolutionRepository",
    "EvolutionTrajectory",
    "IntegrationDecision",
    "PreferenceSignal",
    "PreferenceSignalDetector",
    "ensure_evolution_table",
]
