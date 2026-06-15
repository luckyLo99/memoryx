"""Tests for the evolutionary memory trajectory module."""
from __future__ import annotations

from pathlib import Path

import pytest

from memoryx.evolution import (
    EvolutionDecision,
    EvolutionKind,
    EvolutionManager,
    EvolutionNode,
    EvolutionRepository,
    PreferenceSignal,
    PreferenceSignalDetector,
    ensure_evolution_table,
)


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "test_evo.db"


@pytest.fixture
def repo(db_path) -> EvolutionRepository:
    return EvolutionRepository(db_path)


@pytest.fixture
def manager(repo) -> EvolutionManager:
    return EvolutionManager(repo)


# ===== Models tests =====


class TestEvolutionNode:
    def test_to_row_and_from_row(self):
        node = EvolutionNode(
            id="evo_1",
            entity_id="user_1",
            slot="singer",
            value="张杰",
            kind=EvolutionKind.PREFERENCE,
            valid_from="2026-01-01T00:00:00+00:00",
        )
        row = node.to_row()
        restored = EvolutionNode.from_row(row)
        assert restored.id == node.id
        assert restored.value == "张杰"
        assert restored.kind == EvolutionKind.PREFERENCE
        assert restored.is_active()

    def test_is_active_with_valid_to(self):
        node = EvolutionNode(
            id="evo_2",
            entity_id="u",
            slot="s",
            value="v",
            kind=EvolutionKind.OPINION,
            valid_from="2026-01-01T00:00:00+00:00",
            valid_to="2026-06-01T00:00:00+00:00",
        )
        assert node.is_active(as_of="2026-05-01T00:00:00+00:00")
        assert not node.is_active(as_of="2026-07-01T00:00:00+00:00")

    def test_archived_is_not_active(self):
        node = EvolutionNode(
            id="evo_3",
            entity_id="u",
            slot="s",
            value="v",
            kind=EvolutionKind.FACT,
            valid_from="2026-01-01T00:00:00+00:00",
            active_state="archived",
        )
        assert not node.is_active()


class TestPreferenceSignalDetector:
    def setup_method(self):
        self.det = PreferenceSignalDetector()

    def test_detect_chinese_preference(self):
        sigs = self.det.detect("我最喜欢的歌星是张杰", entity_id="u1")
        assert any(s.slot == "singer" and s.value == "张杰" for s in sigs)

    def test_detect_chinese_food_preference(self):
        sigs = self.det.detect("我最喜欢的食物是火锅", entity_id="u1")
        assert any(s.slot == "food" and s.value == "火锅" for s in sigs)

    def test_detect_english_preference(self):
        sigs = self.det.detect("my favorite singer is Jay Chou", entity_id="u1")
        assert any(s.slot == "singer" and s.value.lower() == "jay chou" for s in sigs)

    def test_detect_chinese_shift(self):
        sigs = self.det.detect("我最喜欢的歌星是张杰，现在最喜欢的是房东的猫", entity_id="u1")
        # The regex may catch the first or the second. At least one node should be created.
        values = [s.value for s in sigs if s.slot == "singer"]
        assert len(values) >= 1

    def test_detect_english_shift(self):
        sigs = self.det.detect("my favorite singer was Jay Chou, now it's Taylor Swift", entity_id="u1")
        assert any(s.slot == "singer" and "Taylor" in s.value for s in sigs)

    def test_chinese_shift_extracts_clean_value(self):
        sigs = self.det.detect("我最喜欢的歌星是张杰，现在最喜欢的是房东的猫", entity_id="u1")
        singer_sigs = [s for s in sigs if s.slot == "singer"]
        # At least one signal should have a clean value
        assert any(s.value in ("张杰", "房东的猫") for s in singer_sigs)

    def test_no_signal_on_empty(self):
        assert self.det.detect("") == []
        assert self.det.detect("   ") == []


# ===== Repository tests =====


class TestEvolutionRepository:
    def test_ensure_table_idempotent(self, db_path):
        ensure_evolution_table(db_path)
        ensure_evolution_table(db_path)
        assert db_path.exists()

    def test_upsert_and_get_active(self, repo):
        node = EvolutionNode(
            id="evo_a", entity_id="u1", slot="singer",
            value="张杰", kind=EvolutionKind.PREFERENCE,
            valid_from="2026-01-01T00:00:00+00:00",
        )
        repo.upsert_node(node)
        latest = repo.get_active("u1", "singer")
        assert latest is not None
        assert latest.value == "张杰"

    def test_upsert_supersedes_previous(self, repo):
        n1 = EvolutionNode(
            id="evo_a", entity_id="u1", slot="singer",
            value="张杰", kind=EvolutionKind.PREFERENCE,
            valid_from="2026-01-01T00:00:00+00:00",
        )
        n2 = EvolutionNode(
            id="evo_b", entity_id="u1", slot="singer",
            value="房东的猫", kind=EvolutionKind.PREFERENCE,
            valid_from="2026-06-01T00:00:00+00:00",
        )
        repo.upsert_node(n1)
        repo.upsert_node(n2)

        active = repo.get_active("u1", "singer")
        assert active is not None
        assert active.value == "房东的猫"

        all_nodes = repo.list_by_entity_slot("u1", "singer", include_inactive=True)
        assert len(all_nodes) == 2
        superseded = [n for n in all_nodes if n.active_state == "superseded"]
        assert len(superseded) == 1
        assert superseded[0].value == "张杰"
        assert superseded[0].valid_to is not None

    def test_list_slots(self, repo):
        repo.upsert_node(EvolutionNode(
            id="e1", entity_id="u1", slot="singer",
            value="X", kind=EvolutionKind.PREFERENCE,
            valid_from="2026-01-01T00:00:00+00:00",
        ))
        repo.upsert_node(EvolutionNode(
            id="e2", entity_id="u1", slot="food",
            value="Y", kind=EvolutionKind.PREFERENCE,
            valid_from="2026-01-01T00:00:00+00:00",
        ))
        slots = repo.list_slots("u1")
        assert set(slots) == {"singer", "food"}

    def test_archive_old(self, repo):
        repo.upsert_node(EvolutionNode(
            id="e1", entity_id="u1", slot="s",
            value="v1", kind=EvolutionKind.PREFERENCE,
            valid_from="2026-01-01T00:00:00+00:00",
        ))
        repo.upsert_node(EvolutionNode(
            id="e2", entity_id="u1", slot="s",
            value="v2", kind=EvolutionKind.PREFERENCE,
            valid_from="2026-02-01T00:00:00+00:00",
        ))
        n = repo.archive_old("u1", "s")
        assert n == 2


# ===== Manager tests (AC-1, AC-2, AC-3) =====


class TestEvolutionManager:
    def test_observe_creates_trajectory_for_first_preference(self, manager):
        nodes = manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
        assert len(nodes) == 1
        assert nodes[0].value == "张杰"
        traj = manager.get_trajectory("u1", "singer")
        assert traj.latest is not None
        assert traj.latest.value == "张杰"

    def test_observe_evolution_appends_without_conflict(self, manager):
        """AC-1: 张杰 → 房东的猫 must not be treated as conflict."""
        manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
        nodes2 = manager.observe("我最喜欢的歌星是房东的猫", entity_id="u1")
        assert len(nodes2) == 1
        assert nodes2[0].value == "房东的猫"
        traj = manager.get_trajectory("u1", "singer")
        # AC-2: trajectory has 2 nodes
        assert len(traj.nodes) == 2
        # Latest is the new value
        assert traj.latest.value == "房东的猫"
        # Old node is superseded but kept (AC-3)
        old = [n for n in traj.nodes if n.value == "张杰"][0]
        assert old.active_state == "superseded"
        assert old.valid_to is not None
        # Old node still retrievable (AC-3)
        assert any(n.value == "张杰" for n in traj.nodes)

    def test_duplicate_value_no_new_node(self, manager):
        manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
        nodes2 = manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
        assert nodes2 == []

    def test_decide_add_evolve_conflict(self, manager):
        manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
        sig_new = PreferenceSignal(
            entity_id="u1", slot="singer", value="房东的猫",
            kind=EvolutionKind.PREFERENCE,
        )
        assert manager.decide(sig_new) == EvolutionDecision.EVOLVE
        sig_dup = PreferenceSignal(
            entity_id="u1", slot="singer", value="张杰",
            kind=EvolutionKind.PREFERENCE,
        )
        assert manager.decide(sig_dup) == EvolutionDecision.ADD
        sig_other = PreferenceSignal(
            entity_id="u1", slot="food", value="火锅",
            kind=EvolutionKind.PREFERENCE,
        )
        assert manager.decide(sig_other) == EvolutionDecision.ADD

    def test_apply_ebbinghaus_decay_does_not_delete(self, manager):
        """AC-3: 6 months later, old node still retrievable."""
        manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
        manager.observe("我最喜欢的歌星是房东的猫", entity_id="u1")
        n = manager.apply_ebbinghaus_decay(entity_id="u1", half_life_hours=24 * 30)
        assert n >= 2
        traj = manager.get_trajectory("u1", "singer")
        # Both nodes still present
        values = {n.value for n in traj.nodes}
        assert "张杰" in values
        assert "房东的猫" in values

    def test_trajectory_latest_is_max_valid_from(self, manager):
        manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
        manager.observe("我最喜欢的歌星是房东的猫", entity_id="u1")
        traj = manager.get_trajectory("u1", "singer")
        assert traj.latest.value == "房东的猫"
        assert traj.to_dict()["latest"] == "房东的猫"

    def test_trajectory_to_dict(self, manager):
        manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
        manager.observe("我最喜欢的歌星是房东的猫", entity_id="u1")
        traj = manager.get_trajectory("u1", "singer")
        d = traj.to_dict()
        assert d["latest"] == "房东的猫"
        assert len(d["history"]) == 2


# ===== Integration tests =====


class TestEvolutionIntegration:
    def test_observe_content_returns_nodes(self, manager):
        from memoryx.evolution.integration import EvolutionIntegration
        integ = EvolutionIntegration(manager)
        nodes = integ.observe_content("我最喜欢的歌星是张杰", entity_id="u1")
        assert len(nodes) == 1

    def test_route_decision(self, manager):
        from memoryx.evolution.integration import EvolutionIntegration
        integ = EvolutionIntegration(manager)
        # First signal → ADD
        sig1 = PreferenceSignal(entity_id="u1", slot="singer", value="张杰",
                                kind=EvolutionKind.PREFERENCE)
        d1 = integ.route(sig1)
        assert d1.is_evolution
        assert d1.decision == EvolutionDecision.ADD
        # Second different value → EVOLVE
        sig2 = PreferenceSignal(entity_id="u1", slot="singer", value="房东的猫",
                                kind=EvolutionKind.PREFERENCE)
        d2 = integ.route(sig2)
        assert d2.is_evolution
        assert d2.decision == EvolutionDecision.EVOLVE
        # is_preference_change returns True for "我最喜欢..."
        assert integ.is_preference_change("我最喜欢的歌星是林俊杰")

    def test_no_manager_is_noop(self):
        from memoryx.evolution.integration import EvolutionIntegration
        integ = EvolutionIntegration(manager=None)
        assert integ.observe_content("我最喜欢的歌星是张杰") == []
        assert not integ.is_preference_change("我最喜欢的歌星是张杰")
