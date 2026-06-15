"""Tests for Ebbinghaus forgetting curve and spaced repetition module."""
from __future__ import annotations

import time

from memoryx.cognitive.ebbinghaus import (
    EbbinghausForgettingCurve,
    MemoryStrength,
    RetrievalOutcome,
    SpacedRepetitionScheduler,
    INTERVAL_TABLE,
)


class TestMemoryStrength:
    def test_default_creation(self):
        s = MemoryStrength()
        assert s.encoding_strength == 0.5
        assert s.retrieval_count == 0
        assert s.strength_s == 1.0
        assert s.next_review_interval == 3600.0

    def test_to_dict_roundtrip(self):
        s = MemoryStrength(encoding_strength=0.8, retrieval_count=3, strength_s=5000.0)
        d = s.to_dict()
        s2 = MemoryStrength.from_dict(d)
        assert s2.encoding_strength == 0.8
        assert s2.retrieval_count == 3
        assert s2.strength_s == 5000.0

    def test_from_dict_empty(self):
        s = MemoryStrength.from_dict({})
        assert s.encoding_strength == 0.5
        assert s.retrieval_count == 0

class TestEbbinghausForgettingCurve:
    def test_initial_strength_importance_mapping(self):
        low = EbbinghausForgettingCurve.initial_strength(0.0)
        high = EbbinghausForgettingCurve.initial_strength(1.0)
        assert low.strength_s <= high.strength_s
        assert low.strength_s >= 3600.0
        assert high.strength_s <= 604800.0

    def test_initial_strength_default(self):
        s = EbbinghausForgettingCurve.initial_strength()
        assert s.encoding_strength == 0.5
        assert s.strength_s > 300000.0
        assert s.half_life > 0

    def test_retention_fresh_memory(self):
        s = EbbinghausForgettingCurve.initial_strength(0.8)
        r = EbbinghausForgettingCurve.retention(s)
        assert r > 0.99

    def test_retention_decays_over_time(self):
        s = EbbinghausForgettingCurve.initial_strength(0.5)
        s.last_accessed_at = time.time() - 86400
        r_old = EbbinghausForgettingCurve.retention(s)
        s.last_accessed_at = time.time() - 86400 * 30
        r_older = EbbinghausForgettingCurve.retention(s)
        assert r_older < r_old

    def test_retention_importance_floor(self):
        low = EbbinghausForgettingCurve.initial_strength(0.1)
        high = EbbinghausForgettingCurve.initial_strength(1.0)
        low.last_accessed_at = 0
        high.last_accessed_at = 0
        r_low = EbbinghausForgettingCurve.retention(low)
        r_high = EbbinghausForgettingCurve.retention(high)
        assert r_high >= r_low

    def test_update_after_perfect_retrieval(self):
        s = EbbinghausForgettingCurve.initial_strength(0.5)
        old_strength = s.strength_s
        s2 = EbbinghausForgettingCurve.update_after_retrieval(s, RetrievalOutcome.PERFECT)
        assert s2.retrieval_count == 1
        assert s2.strength_s > old_strength
        assert s2.next_review_interval >= 3600

    def test_update_after_failed_retrieval(self):
        s = EbbinghausForgettingCurve.initial_strength(0.5)
        s.retrieval_count = 3
        s2 = EbbinghausForgettingCurve.update_after_retrieval(s, RetrievalOutcome.FAIL)
        assert s2.retrieval_count == 2
        assert s2.next_review_interval < 3600
        assert s2.last_outcome == RetrievalOutcome.FAIL

    def test_retrieval_practice_effect(self):
        s = EbbinghausForgettingCurve.initial_strength(0.5)
        strengths = []
        for i in range(5):
            s = EbbinghausForgettingCurve.update_after_retrieval(s, RetrievalOutcome.PERFECT)
            strengths.append(s.strength_s)
        for i in range(1, len(strengths)):
            assert strengths[i] > strengths[i-1]

    def test_decay_multiplier_bounds(self):
        s = EbbinghausForgettingCurve.initial_strength(0.5)
        d = EbbinghausForgettingCurve.decay_multiplier(s)
        assert d >= 0.20
        assert d <= 1.15

    def test_is_due_for_review(self):
        now = time.time()
        s = MemoryStrength(next_review_interval=0, last_accessed_at=now)
        assert EbbinghausForgettingCurve.is_due_for_review(s)
        s2 = MemoryStrength(next_review_interval=86400*365, last_accessed_at=now)
        assert not EbbinghausForgettingCurve.is_due_for_review(s2)


class TestSpacedRepetitionScheduler:
    def test_schedule_next_review_increases(self):
        s = EbbinghausForgettingCurve.initial_strength(0.5)
        intervals = []
        for i in range(5):
            s = EbbinghausForgettingCurve.update_after_retrieval(s, RetrievalOutcome.PERFECT)
            intervals.append(s.next_review_interval)
        for i in range(1, len(intervals)):
            assert intervals[i] >= intervals[i-1]

    def test_box_for_memory(self):
        s = MemoryStrength(next_review_interval=0)
        assert SpacedRepetitionScheduler.box_for_memory(s) == 0
        s2 = MemoryStrength(next_review_interval=7776000)
        assert SpacedRepetitionScheduler.box_for_memory(s2) >= 5

    def test_batch_due_memories(self):
        now = time.time()
        due_now = MemoryStrength(next_review_interval=0, last_accessed_at=now - 86400)
        not_due = MemoryStrength(next_review_interval=999999999, last_accessed_at=now)
        items = [("m1", not_due), ("m2", due_now)]
        due = SpacedRepetitionScheduler.batch_due_memories(items, max_items=10)
        ids = [mid for mid, _ in due]
        assert "m2" in ids
        assert "m1" not in ids

    def test_batch_due_memories_limits(self):
        items = [(f"m{i}", MemoryStrength(next_review_interval=0)) for i in range(20)]
        due = SpacedRepetitionScheduler.batch_due_memories(items, max_items=5)
        assert len(due) == 5


class TestEbbinghausScorerIntegration:
    def test_ebbinghaus_decay_multiplier_function(self):
        from memoryx.retrieval.scorer import ebbinghaus_decay_multiplier
        edm = ebbinghaus_decay_multiplier(importance=0.8, retrieval_count=3)
        assert 0.20 <= edm <= 1.15

    def test_ebbinghaus_none_params(self):
        from memoryx.retrieval.scorer import ebbinghaus_decay_multiplier
        result = ebbinghaus_decay_multiplier(last_accessed_at=None, updated_at=None)
        assert result == 1.0


class TestIntervalTable:
    def test_intervals_increase(self):
        for outcome in RetrievalOutcome:
            intervals = INTERVAL_TABLE[outcome]
            for i in range(1, len(intervals)):
                assert intervals[i] >= intervals[i-1]

    def test_perfect_longer_than_fail(self):
        for i in range(len(INTERVAL_TABLE[RetrievalOutcome.PERFECT])):
            assert INTERVAL_TABLE[RetrievalOutcome.PERFECT][i] >= INTERVAL_TABLE[RetrievalOutcome.FAIL][i]
