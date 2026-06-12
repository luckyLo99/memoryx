"""Tests for the evolution REST route module.

We deliberately keep this file dependency-light:

- We assert the module imports cleanly (so registering the router in the app
  factory will not break the rest of the codebase).
- We assert the Pydantic request/response models validate correctly.
- We exercise the small helpers (``_node_to_response``,
  ``_get_manager_or_503``) and the lazy-cache behaviour with monkeypatching.

We do **not** spin up a full FastAPI app / uvicorn: that is covered by the
end-to-end tests in ``tests/e2e``. This unit test stays importable in any
environment where the FastAPI + pydantic deps are present (they are required by
the rest of the API package anyway).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


def test_module_imports_cleanly():
    """The route module must be importable without booting the REST app."""
    # Drop any cached version to make sure the import path is fresh.
    sys.modules.pop("memoryx.api.routes.evolution", None)
    mod = importlib.import_module("memoryx.api.routes.evolution")
    assert mod is not None
    # Public surface
    assert hasattr(mod, "router")
    assert hasattr(mod, "build_evolution_router")
    assert hasattr(mod, "EvolutionNodeResponse")
    assert hasattr(mod, "TrajectoryResponse")
    assert hasattr(mod, "ObserveRequest")
    assert hasattr(mod, "ObserveResponse")
    assert hasattr(mod, "SlotsResponse")


def test_router_has_expected_routes():
    """Router must expose the three documented endpoints with the right paths."""
    from memoryx.api.routes.evolution import router

    paths = {route.path for route in router.routes}
    assert "/evolution/trajectory" in paths
    assert "/evolution/observe" in paths
    assert "/evolution/slots" in paths

    # Methods
    methods_by_path: dict[str, set[str]] = {}
    for route in router.routes:
        methods_by_path.setdefault(route.path, set()).update(route.methods or set())
    assert "GET" in methods_by_path["/evolution/trajectory"]
    assert "POST" in methods_by_path["/evolution/observe"]
    assert "GET" in methods_by_path["/evolution/slots"]


def test_build_evolution_router_returns_router():
    """The registration helper must return a usable APIRouter."""
    from fastapi import APIRouter

    from memoryx.api.routes.evolution import build_evolution_router, router

    returned = build_evolution_router()
    assert isinstance(returned, APIRouter)
    # The same module-level object — registration is idempotent.
    assert returned is router


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestObserveRequest:
    def test_minimal_payload(self):
        from memoryx.api.routes.evolution import ObserveRequest

        req = ObserveRequest(content="我最喜欢的歌星是张杰")
        assert req.content == "我最喜欢的歌星是张杰"
        assert req.entity_id == "user"
        assert req.memory_id is None

    def test_full_payload(self):
        from memoryx.api.routes.evolution import ObserveRequest

        req = ObserveRequest(
            content="my favorite singer is Jay Chou",
            entity_id="u_42",
            memory_id="mem_abc",
        )
        assert req.entity_id == "u_42"
        assert req.memory_id == "mem_abc"

    def test_empty_content_rejected(self):
        from pydantic import ValidationError

        from memoryx.api.routes.evolution import ObserveRequest

        with pytest.raises(ValidationError):
            ObserveRequest(content="")


class TestEvolutionNodeResponse:
    def test_round_trip_defaults(self):
        from memoryx.api.routes.evolution import EvolutionNodeResponse

        node = EvolutionNodeResponse(
            id="evo_1",
            entity_id="u1",
            slot="singer",
            value="张杰",
            kind="PREFERENCE",
            valid_from="2026-01-01T00:00:00+00:00",
            created_at="2026-01-01T00:00:00+00:00",
        )
        assert node.confidence == 1.0
        assert node.active_state == "active"
        assert node.decay_score == 0.0
        assert node.valid_to is None
        assert node.context == ""

    def test_serialises_to_dict(self):
        from memoryx.api.routes.evolution import EvolutionNodeResponse

        node = EvolutionNodeResponse(
            id="e1",
            entity_id="u1",
            slot="food",
            value="火锅",
            kind="PREFERENCE",
            valid_from="t1",
            created_at="t1",
            valid_to="t2",
            confidence=0.9,
            source_memory_id="mem_x",
            context="ctx",
            active_state="superseded",
            decay_score=0.1,
        )
        d = node.model_dump()
        assert d["id"] == "e1"
        assert d["value"] == "火锅"
        assert d["valid_to"] == "t2"
        assert d["confidence"] == 0.9
        assert d["active_state"] == "superseded"


class TestTrajectoryResponse:
    def test_empty_history_is_valid(self):
        from memoryx.api.routes.evolution import TrajectoryResponse

        t = TrajectoryResponse(entity_id="u1", slot="singer")
        assert t.latest is None
        assert t.history == []

    def test_with_history(self):
        from memoryx.api.routes.evolution import EvolutionNodeResponse, TrajectoryResponse

        n = EvolutionNodeResponse(
            id="e1",
            entity_id="u1",
            slot="singer",
            value="张杰",
            kind="PREFERENCE",
            valid_from="t1",
            created_at="t1",
        )
        t = TrajectoryResponse(entity_id="u1", slot="singer", latest="张杰", history=[n])
        assert t.latest == "张杰"
        assert len(t.history) == 1
        assert t.history[0].value == "张杰"


class TestSlotsResponse:
    def test_empty_slots(self):
        from memoryx.api.routes.evolution import SlotsResponse

        s = SlotsResponse(entity_id="u1")
        assert s.entity_id == "u1"
        assert s.slots == []

    def test_with_slots(self):
        from memoryx.api.routes.evolution import SlotsResponse

        s = SlotsResponse(entity_id="u1", slots=["singer", "food"])
        assert s.slots == ["singer", "food"]


class TestObserveResponse:
    def test_defaults(self):
        from memoryx.api.routes.evolution import ObserveResponse

        r = ObserveResponse(entity_id="u1")
        assert r.written == []
        assert r.detected == 0
        assert r.entity_id == "u1"

    def test_with_written_nodes(self):
        from memoryx.api.routes.evolution import EvolutionNodeResponse, ObserveResponse

        n = EvolutionNodeResponse(
            id="e1",
            entity_id="u1",
            slot="singer",
            value="X",
            kind="PREFERENCE",
            valid_from="t",
            created_at="t",
        )
        r = ObserveResponse(entity_id="u1", written=[n], detected=2)
        assert r.detected == 2
        assert len(r.written) == 1


# ---------------------------------------------------------------------------
# Internal helper tests
# ---------------------------------------------------------------------------


class TestNodeToResponse:
    def test_converts_enum_kind(self):
        from memoryx.evolution import EvolutionKind, EvolutionNode

        from memoryx.api.routes.evolution import _node_to_response

        node = EvolutionNode(
            id="e1",
            entity_id="u1",
            slot="singer",
            value="张杰",
            kind=EvolutionKind.PREFERENCE,
            valid_from="t1",
        )
        resp = _node_to_response(node)
        assert resp.id == "e1"
        assert resp.kind == "PREFERENCE"
        assert resp.value == "张杰"
        assert resp.valid_to is None

    def test_converts_string_kind(self):
        from memoryx.evolution import EvolutionNode

        from memoryx.api.routes.evolution import _node_to_response

        # Construct a node with a raw string kind to confirm tolerance.
        node = EvolutionNode(
            id="e2",
            entity_id="u1",
            slot="s",
            value="v",
            kind="FACT",  # type: ignore[arg-type]
            valid_from="t1",
        )
        resp = _node_to_response(node)
        assert resp.kind == "FACT"


class TestGetManagerOr503:
    def test_returns_cached_manager(self):
        """A second call must reuse the cached manager, not rebuild it."""
        from memoryx.api import routes.evolution as evo_mod

        # Pre-seed the cache to confirm we never re-enter the build path.
        sentinel = object()
        evo_mod._manager_cache["default"] = sentinel  # type: ignore[assignment]
        try:
            assert evo_mod._get_manager_or_503() is sentinel
        finally:
            evo_mod._manager_cache.pop("default", None)

    def test_503_when_build_fails(self, monkeypatch):
        """If building the manager raises, we surface 503 — not a 500."""
        from fastapi import HTTPException

        from memoryx.api import routes.evolution as evo_mod

        # Ensure cache is empty so we exercise the build path.
        evo_mod._manager_cache.pop("default", None)

        def _boom():
            raise RuntimeError("simulated db failure")

        monkeypatch.setattr(evo_mod, "_build_manager", _boom)
        with pytest.raises(HTTPException) as ei:
            evo_mod._get_manager_or_503()
        assert ei.value.status_code == 503
        assert "evolution manager not configured" in str(ei.value.detail)


class TestBuildManager:
    def test_uses_settings_db_path(self, tmp_path: Path):
        """The builder must point at MemoryXSettings.db_path, not a hard-coded path."""
        from memoryx.api import routes.evolution as evo_mod
        from memoryx.config import MemoryXSettings

        # Build a settings object with a custom home so the DB lives in tmp_path.
        settings = MemoryXSettings(home=tmp_path)

        with patch.object(evo_mod, "get_settings", return_value=settings):
            manager = evo_mod._build_manager()
        assert isinstance(manager, evo_mod.EvolutionManager)
        assert manager.repository.db_path == settings.db_path
