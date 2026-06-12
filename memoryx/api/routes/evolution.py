"""Optional REST API routes for the MemoryX evolutionary trajectory feature.

This module is intentionally self-contained: importing it does NOT require the
full MemoryX REST app to be running, and registering the router is opt-in.

Endpoints
---------
- GET  /evolution/trajectory?entity_id=...&slot=...  → list trajectory nodes
- POST /evolution/observe                            → submit content to be
                                                       observed for preference
                                                       signals
- GET  /evolution/slots?entity_id=...                → list slots tracked for
                                                       an entity

Registration
------------
The router is *not* wired into ``memoryx.api.rest_app`` by default. To enable
it, add (e.g. in ``app_factory.create_app``):

    from memoryx.api.routes.evolution import router as evolution_router
    app.include_router(evolution_router)

Lazy wiring
-----------
The ``EvolutionManager`` is constructed lazily on first request. It uses the
SQLite path exposed by :class:`memoryx.config.MemoryXSettings` (the same file
``MemoryRepository`` writes to). If construction fails for any reason the
endpoints return ``503 Service Unavailable`` with a clear message — they never
crash the surrounding app.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from memoryx.config import MemoryXSettings, get_settings
from memoryx.evolution import EvolutionManager, EvolutionNode, EvolutionRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/evolution", tags=["evolution-trajectory"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class EvolutionNodeResponse(BaseModel):
    """Serialised view of a single :class:`EvolutionNode`."""

    id: str
    entity_id: str
    slot: str
    value: str
    kind: str
    valid_from: str
    valid_to: Optional[str] = None
    confidence: float = 1.0
    source_memory_id: Optional[str] = None
    context: str = ""
    created_at: str
    active_state: str = "active"
    decay_score: float = 0.0


class TrajectoryResponse(BaseModel):
    """Full trajectory for one (entity, slot) pair, plus the latest value."""

    entity_id: str
    slot: str
    latest: Optional[str] = None
    history: list[EvolutionNodeResponse] = Field(default_factory=list)


class ObserveRequest(BaseModel):
    """Body for ``POST /evolution/observe``."""

    content: str = Field(..., min_length=1, description="Free-form text to scan for preference signals")
    entity_id: str = Field(default="user", description="Entity the observation belongs to")
    memory_id: Optional[str] = Field(default=None, description="Optional source memory id")


class ObserveResponse(BaseModel):
    """Result of submitting content for observation."""

    entity_id: str
    written: list[EvolutionNodeResponse] = Field(default_factory=list)
    detected: int = Field(default=0, description="Number of signals the detector found")


class SlotsResponse(BaseModel):
    """List of slots tracked for an entity."""

    entity_id: str
    slots: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Lazy EvolutionManager construction
# ---------------------------------------------------------------------------

# Process-local cache so we only build the manager (and open the DB) once.
_manager_cache: dict[str, EvolutionManager] = {}


def _build_manager(settings: Optional[MemoryXSettings] = None) -> EvolutionManager:
    """Construct an :class:`EvolutionManager` using the configured SQLite path.

    Reads ``MemoryXSettings.db_path`` (the same file the ``MemoryRepository``
    writes to) and wraps it in an :class:`EvolutionRepository`.
    """
    s = settings if settings is not None else get_settings()
    db_path = s.db_path
    repo = EvolutionRepository(db_path)
    return EvolutionManager(repo)


def _get_manager_or_503() -> EvolutionManager:
    """Return the cached manager, building it on first use.

    On any failure (settings missing, DB not writable, etc.) raise an
    ``HTTPException(503)`` with a clear, safe message. We never let the
    surrounding app crash because evolution is not configured.
    """
    try:
        cached = _manager_cache.get("default")
        if cached is not None:
            return cached
        manager = _build_manager()
        _manager_cache["default"] = manager
        return manager
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover — defensive guard
        logger.exception("evolution manager unavailable")
        raise HTTPException(
            status_code=503,
            detail=f"evolution manager not configured: {exc}",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _node_kind_str(node: EvolutionNode) -> str:
    """Return the string form of an EvolutionNode.kind, tolerating both enum and str."""
    kind = node.kind
    if hasattr(kind, "value"):
        return str(kind.value)
    return str(kind)


def _node_to_response(node: EvolutionNode) -> EvolutionNodeResponse:
    return EvolutionNodeResponse(
        id=node.id,
        entity_id=node.entity_id,
        slot=node.slot,
        value=node.value,
        kind=_node_kind_str(node),
        valid_from=node.valid_from,
        valid_to=node.valid_to,
        confidence=node.confidence,
        source_memory_id=node.source_memory_id,
        context=node.context,
        created_at=node.created_at,
        active_state=node.active_state,
        decay_score=node.decay_score,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/trajectory",
    response_model=TrajectoryResponse,
    summary="List trajectory nodes for an (entity, slot) pair",
)
def get_trajectory(
    entity_id: str = Query(..., min_length=1, description="Entity id, e.g. 'user'"),
    slot: str = Query(..., min_length=1, description="Slot name, e.g. 'singer'"),
) -> TrajectoryResponse:
    """Return all trajectory nodes (including superseded) for one (entity, slot)."""
    manager = _get_manager_or_503()
    try:
        traj = manager.get_trajectory(entity_id, slot)
    except Exception as exc:
        logger.exception("evolution.get_trajectory failed")
        raise HTTPException(status_code=500, detail=f"trajectory lookup failed: {exc}")

    nodes_sorted = sorted(traj.nodes, key=lambda n: n.valid_from)
    return TrajectoryResponse(
        entity_id=traj.entity_id,
        slot=traj.slot,
        latest=traj.latest.value if traj.latest else None,
        history=[_node_to_response(n) for n in nodes_sorted],
    )


@router.post(
    "/observe",
    response_model=ObserveResponse,
    summary="Submit content to be observed for preference signals",
)
def observe(body: ObserveRequest) -> ObserveResponse:
    """Detect preference / opinion / fact-change signals in ``content`` and append
    trajectory nodes for any new values.

    Returns the list of *newly written* nodes. Duplicate values (matching the
    currently active node for the same slot) are skipped — this is by design
    and mirrors :meth:`EvolutionManager.observe`.
    """
    if not body.content or not body.content.strip():
        raise HTTPException(status_code=400, detail="content must not be empty")

    manager = _get_manager_or_503()

    # Run the detector first so we can report how many signals were considered
    # (not just how many nodes were actually written — duplicates are skipped).
    try:
        signals = manager.detector.detect(
            body.content,
            entity_id=body.entity_id,
            memory_id=body.memory_id,
        )
        written = manager.observe(
            body.content,
            entity_id=body.entity_id,
            memory_id=body.memory_id,
        )
    except Exception as exc:
        logger.exception("evolution.observe failed")
        raise HTTPException(status_code=500, detail=f"observe failed: {exc}")

    return ObserveResponse(
        entity_id=body.entity_id,
        written=[_node_to_response(n) for n in written],
        detected=len(signals),
    )


@router.get(
    "/slots",
    response_model=SlotsResponse,
    summary="List slots tracked for an entity",
)
def list_slots(
    entity_id: str = Query(..., min_length=1, description="Entity id, e.g. 'user'"),
) -> SlotsResponse:
    """Return the distinct slots that have at least one trajectory node for
    the given ``entity_id``."""
    manager = _get_manager_or_503()
    try:
        slots = manager.list_slots(entity_id)
    except Exception as exc:
        logger.exception("evolution.list_slots failed")
        raise HTTPException(status_code=500, detail=f"slots lookup failed: {exc}")

    return SlotsResponse(entity_id=entity_id, slots=list(slots))


# ---------------------------------------------------------------------------
# Programmatic registration helper
# ---------------------------------------------------------------------------


def build_evolution_router() -> APIRouter:
    """Return the evolution router.

    Exists so that future code (e.g. ``app_factory.create_app``) can do:

        from memoryx.api.routes.evolution import build_evolution_router
        app.include_router(build_evolution_router())

    The returned router is a fresh module-level object reference; routes
    themselves are shared.
    """
    return router
