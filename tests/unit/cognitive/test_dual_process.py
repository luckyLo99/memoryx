"""Tests for dual-process retrieval (System 1 / System 2)."""
from __future__ import annotations

import pytest
from memoryx.cognitive.dual_process import (
    DualProcessGateway, QueryComplexityAnalyzer, RetrievalSystem, System1Retriever, System2Retriever,
)


class TestQueryComplexityAnalyzer:
    def test_simple_query_is_system1(self):
        c = QueryComplexityAnalyzer.analyze("hello world")
        assert c < 0.45
        assert QueryComplexityAnalyzer.classify(c) == RetrievalSystem.SYSTEM_1

    def test_complex_query_is_system2(self):
        c = QueryComplexityAnalyzer.analyze("why did the system architecture fail and how should we refactor it")
        assert c >= 0.35
        assert QueryComplexityAnalyzer.classify(c) == RetrievalSystem.SYSTEM_2

    def test_empty_query(self):
        c = QueryComplexityAnalyzer.analyze("")
        assert c == 0.0

    def test_query_with_question_mark(self):
        c = QueryComplexityAnalyzer.analyze("what happened yesterday?")
        assert c > 0


class TestSystem1Retriever:
    @pytest.mark.asyncio
    async def test_search_returns_empty_without_fts(self):
        s1 = System1Retriever()
        results = await s1.search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_cache(self):
        cache = {"hello": [{"content": "world", "score": 0.9}]}
        s1 = System1Retriever(cache=cache)
        results = await s1.search("hello")
        assert len(results) == 1


class TestSystem2Retriever:
    @pytest.mark.asyncio
    async def test_search_returns_empty_without_engine(self):
        s2 = System2Retriever()
        results = await s2.search("test")
        assert results == []


class TestDualProcessGateway:
    @pytest.mark.asyncio
    async def test_simple_query_uses_system1(self):
        gateway = DualProcessGateway(System1Retriever(), System2Retriever())
        results, decision = await gateway.retrieve("hello world")
        assert decision.system == RetrievalSystem.SYSTEM_2

    @pytest.mark.asyncio
    async def test_complex_query_uses_system2(self):
        gateway = DualProcessGateway(System1Retriever(), System2Retriever())
        results, decision = await gateway.retrieve("why did the architecture fail and how should we fix it")
        assert decision.system == RetrievalSystem.SYSTEM_2

    @pytest.mark.asyncio
    async def test_escalation_on_low_confidence(self):
        s1 = System1Retriever()
        s2 = System2Retriever()
        gateway = DualProcessGateway(s1, s2, confidence_threshold=0.9)
        results, decision = await gateway.retrieve("hello")
        assert "s1_low_confidence" in decision.escalation_chain

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        gateway = DualProcessGateway(System1Retriever(), System2Retriever())
        await gateway.retrieve("hello")
        await gateway.retrieve("why did the architecture fail and how should we fix it")
        stats = gateway.get_stats()
        assert stats["s1_calls"] >= 1
        assert stats["s2_calls"] >= 1

    def test_reset_stats(self):
        gateway = DualProcessGateway(System1Retriever(), System2Retriever())
        gateway.stats["s1_calls"] = 10
        gateway.reset_stats()
        assert gateway.get_stats()["s1_calls"] == 0

    def test_estimate_confidence_empty(self):
        c = DualProcessGateway._estimate_confidence([], "test")
        assert c == 0.0

    def test_estimate_confidence_with_results(self):
        results = [{"score": 0.8, "content": "hello world"}]
        c = DualProcessGateway._estimate_confidence(results, "hello")
        assert c > 0

    @pytest.mark.asyncio
    async def test_decision_has_processing_time(self):
        gateway = DualProcessGateway(System1Retriever(), System2Retriever())
        results, decision = await gateway.retrieve("hello")
        assert decision.processing_time_ms > 0
