"""Evolution-specific forgetting: Ebbinghaus decay and soft-archival.

Evolution nodes are NEVER hard-deleted — only soft-archived by setting
``active_state = 'archived'``.  This preserves the full trajectory history
so that ``get_trajectory()`` (with ``include_inactive=True``) can always
reconstruct the complete timeline, even for nodes that are no longer
active.

This module is additive to the existing cognitive forgetting layer and
does NOT modify any existing forgetting code.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .manager import EvolutionManager

_logger = logging.getLogger(__name__)


def apply_evolution_decay(
    manager: EvolutionManager,
    entity_id: str = "user",
    half_life_hours: float = 24 * 30,
) -> int:
    """Apply Ebbinghaus decay to all active evolution nodes.

    Delegates to ``EvolutionManager.apply_ebbinghaus_decay()`` which
    computes R = e^(-t/S) for each node and persists the decay_score.

    Args:
        manager: The EvolutionManager instance.
        entity_id: Entity whose nodes to decay (default "user").
        half_life_hours: Half-life in hours for the Ebbinghaus curve.
            Default is 720 hours (≈30 days).

    Returns:
        Number of nodes whose decay_score was updated.
    """
    return manager.apply_ebbinghaus_decay(entity_id=entity_id, half_life_hours=half_life_hours)


def archive_evolved_nodes(
    manager: EvolutionManager,
    entity_id: str,
    slot: str,
    older_than_days: float = 180.0,
) -> int:
    """Soft-archive old superseded evolution nodes.

    Nodes whose ``active_state`` is ``'superseded'`` **and** whose
    ``valid_to`` is older than *older_than_days* days ago are set to
    ``active_state = 'archived'``.

    **Evolution nodes are NEVER hard-deleted**, only soft-archived.
    Archived nodes remain visible via ``get_trajectory(include_inactive=True)``
    but are excluded from ``get_active()`` queries.

    Args:
        manager: The EvolutionManager instance.
        entity_id: Entity whose nodes to consider.
        slot: Slot name within the entity.
        older_than_days: Minimum age (in days) for a superseded node
            to be eligible for archival. Default 180 days (≈6 months).

    Returns:
        Number of nodes soft-archived.
    """
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - older_than_days * 86400.0

    nodes = manager.repository.list_by_entity_slot(entity_id, slot, include_inactive=True)
    archived = 0
    for node in nodes:
        if node.active_state != "superseded":
            continue
        if node.valid_to is None:
            continue
        try:
            vt = datetime.fromisoformat(node.valid_to.replace("Z", "+00:00"))
            if vt.tzinfo is None:
                vt = vt.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            _logger.warning("Skipping node %s with invalid valid_to: %s", node.id, node.valid_to)
            continue
        if vt.timestamp() < cutoff:
            manager.repository.archive_old(entity_id, slot)
            archived += 1
            break  # archive_old operates on the whole (entity, slot) pair
    return archived
