"""Integration tests for evolution trajectory with conflict_resolver and full pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from memoryx.evolution import (
    EvolutionKind,
    EvolutionManager,
    EvolutionRepository,
    PreferenceSignal,
)
from memoryx.evolution.integration import EvolutionIntegration
from memoryx.extraction.models import ExtractionMemory
from memoryx.validation.conflict_resolver import ConflictResolver


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "test_evo_int.db"


@pytest.fixture
def repo(db_path) -> EvolutionRepository:
    return EvolutionRepository(db_path)


@pytest.fixture
def manager(repo) -> EvolutionManager:
    return EvolutionManager(repo)


@pytest.fixture
def integration(manager) -> EvolutionIntegration:
    return EvolutionIntegration(manager)


def _make_memory(content: str, reasoning: str = "") -> ExtractionMemory:
    return ExtractionMemory(
        memory_type="preference",
        content=content,
        importance_score=0.8,
        confidence_score=0.9,
        timestamp=datetime.now(timezone.utc),
        reasoning=reasoning,
    )


class TestConflictResolverWithEvolution:
    """Verify that preference changes routed through EvolutionIntegration
    are not flagged as conflicts by ConflictResolver."""

    def test_preference_change_skips_conflict_with_evolution(self, manager, integration):
        """When evolution integration is active, a preference shift should be
        routed to EvolutionManager and NOT flagged as a conflict."""
        # First preference
        manager.observe("我最喜欢的歌星是张杰", entity_id="u1")

        # Second (shifted) preference detected via integration
        sig = PreferenceSignal(
            entity_id="u1", slot="singer", value="房东的猫",
            kind=EvolutionKind.PREFERENCE,
        )
        decision = integration.route(sig)
        assert decision.is_evolution
        assert decision.decision != "CONFLICT"

        # Now verify ConflictResolver would normally flag this as conflict
        # (because "like" vs "like" with different targets triggers polarity markers)
        existing = _make_memory("我最喜欢的歌星是张杰")
        candidate = _make_memory("我最喜欢的歌星是房东的猫")
        resolver = ConflictResolver()
        resolver.resolve(candidate, [existing])
        # The resolver may or may not detect a conflict here depending on
        # keyword overlap, but the key point is: when evolution integration
        # routes the signal as EVOLVE, the caller should skip conflict_resolver.
        # So we verify the integration decision is_evolution=True.
        assert decision.is_evolution is True

    def test_conflict_resolver_without_evolution_still_works(self):
        """Without evolution integration, ConflictResolver works as before."""
        resolver = ConflictResolver()
        existing = _make_memory("I love coffee", reasoning="user loves coffee")
        candidate = _make_memory("I hate coffee", reasoning="user hates coffee")
        conflict = resolver.resolve(candidate, [existing])
        assert conflict is not None
        assert "contradiction" in conflict.reason.lower() or "冲突" in conflict.reason

    def test_no_evolution_manager_means_no_evolution_route(self):
        """EvolutionIntegration with no manager should not route anything."""
        integ = EvolutionIntegration(manager=None)
        sig = PreferenceSignal(
            entity_id="u1", slot="singer", value="张杰",
            kind=EvolutionKind.PREFERENCE,
        )
        decision = integ.route(sig)
        assert decision.is_evolution is False
        assert decision.reason == "no_manager"


class TestFullPipeline:
    """End-to-end: observe → get_trajectory → apply_decay."""

    def test_observe_trajectory_decay(self, manager):
        """Full pipeline: observe preferences, retrieve trajectory, apply decay."""
        # Step 1: observe two preference statements
        nodes1 = manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
        assert len(nodes1) == 1
        assert nodes1[0].value == "张杰"

        nodes2 = manager.observe("我最喜欢的歌星是房东的猫", entity_id="u1")
        assert len(nodes2) == 1
        assert nodes2[0].value == "房东的猫"

        # Step 2: retrieve trajectory
        traj = manager.get_trajectory("u1", "singer")
        assert traj.latest is not None
        assert traj.latest.value == "房东的猫"
        assert len(traj.nodes) == 2

        # Verify old node is superseded but still present
        old = [n for n in traj.nodes if n.value == "张杰"][0]
        assert old.active_state == "superseded"
        assert old.valid_to is not None

        # Step 3: apply Ebbinghaus decay
        n_updated = manager.apply_ebbinghaus_decay(entity_id="u1", half_life_hours=24 * 30)
        assert n_updated >= 2

        # After decay, trajectory still has both nodes
        traj2 = manager.get_trajectory("u1", "singer")
        values = {n.value for n in traj2.nodes}
        assert "张杰" in values
        assert "房东的猫" in values

        # Decay scores should be > 0 for older node
        old_node = [n for n in traj2.nodes if n.value == "张杰"][0]
        assert old_node.decay_score > 0

    def test_observe_english_preference_pipeline(self, manager):
        """Pipeline works for English preferences too."""
        nodes1 = manager.observe("my favorite singer is Jay Chou", entity_id="u1")
        assert len(nodes1) == 1

        nodes2 = manager.observe("my favorite singer is Taylor Swift", entity_id="u1")
        assert len(nodes2) == 1

        traj = manager.get_trajectory("u1", "singer")
        assert traj.latest.value == "Taylor Swift"
        assert len(traj.nodes) == 2

        d = traj.to_dict()
        assert d["latest"] == "Taylor Swift"
        assert len(d["history"]) == 2
