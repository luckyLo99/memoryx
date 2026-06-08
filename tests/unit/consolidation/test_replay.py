"""Tests for consolidation replay, reconsolidation, and scheduling."""
from __future__ import annotations

import pytest
from memoryx.consolidation.replay import (
    ConsolidationScheduler, HippocampalReplay, MemoryReconsolidation,
    ReplayBuffer, ReplayEvent,
)


class TestReplayBuffer:
    def test_add_and_size(self):
        buf = ReplayBuffer(max_size=10)
        buf.add(ReplayEvent(event_id="e1", content="test", importance=0.8))
        assert buf.size() == 1

    def test_sample_orders_by_importance(self):
        buf = ReplayBuffer(max_size=10)
        buf.add(ReplayEvent(event_id="e1", content="low", importance=0.2))
        buf.add(ReplayEvent(event_id="e2", content="high", importance=0.9))
        samples = buf.sample(n=2)
        assert samples[0].event_id == "e2"

    def test_sample_importance_filter(self):
        buf = ReplayBuffer(max_size=10)
        buf.add(ReplayEvent(event_id="e1", importance=0.1))
        samples = buf.sample(n=5, min_importance=0.5)
        assert len(samples) == 0

    def test_clear(self):
        buf = ReplayBuffer(max_size=10)
        buf.add(ReplayEvent(event_id="e1", importance=0.5))
        buf.clear()
        assert buf.size() == 0

    def test_max_size(self):
        buf = ReplayBuffer(max_size=3)
        for i in range(5):
            buf.add(ReplayEvent(event_id="e" + str(i), importance=float(i)))
        assert buf.size() == 3


class TestHippocampalReplay:
    @pytest.mark.asyncio
    async def test_replay_empty_buffer(self):
        buf = ReplayBuffer()
        replay = HippocampalReplay(buf)
        count = await replay.replay(n=10)
        assert count == 0

    @pytest.mark.asyncio
    async def test_replay_with_events(self):
        buf = ReplayBuffer()
        buf.add(ReplayEvent(event_id="e1", importance=0.9))
        replay = HippocampalReplay(buf)
        count = await replay.replay(n=10, min_importance=0.0)
        assert count == 1


class TestMemoryReconsolidation:
    @pytest.mark.asyncio
    async def test_reconsolidate_no_repository(self):
        rc = MemoryReconsolidation()
        result = await rc.reconsolidate("m1", "new content")
        assert result["updated"] == False


class TestConsolidationScheduler:
    @pytest.mark.asyncio
    async def test_run_once_empty(self):
        scheduler = ConsolidationScheduler()
        results = await scheduler.run_once()
        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_start_stop(self):
        scheduler = ConsolidationScheduler()
        scheduler.start()
        assert scheduler.is_running() == True
        await scheduler.stop()
        assert scheduler.is_running() == False

    def test_not_running_initially(self):
        scheduler = ConsolidationScheduler()
        assert scheduler.is_running() == False
