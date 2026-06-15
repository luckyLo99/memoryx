"""Tests for cognitive load optimization and procedural memory."""
from __future__ import annotations
from memoryx.cognitive.cognitive_load import CognitiveLoadOptimizer, CHUNK_LIMIT
from memoryx.cognitive.procedural_memory import ProceduralMemory


class TestCognitiveLoadOptimizer:
    def test_analyze_empty(self):
        clo = CognitiveLoadOptimizer()
        profile = clo.analyze_task("hello", [])
        assert profile.total_chunks == 0

    def test_analyze_with_chunks(self):
        clo = CognitiveLoadOptimizer()
        chunks = [{"id": str(i)} for i in range(5)]
        profile = clo.analyze_task("complex task with many words for testing cognitive load", chunks)
        assert profile.total_chunks <= CHUNK_LIMIT

    def test_chunk_items(self):
        result = CognitiveLoadOptimizer.chunk_items(["a","b","c","d","e","f"], chunk_size=3)
        assert len(result) == 2

    def test_optimize_budget(self):
        clo = CognitiveLoadOptimizer()
        profile = clo.analyze_task("test", [{} for _ in range(10)])
        budget = CognitiveLoadOptimizer.optimize_budget(4096, profile)
        assert budget >= 1024

    def test_miller_capacity(self):
        lo, hi = CognitiveLoadOptimizer.miller_capacity(7)
        assert lo <= 7 <= hi


class TestProceduralMemory:
    def test_extract_pattern(self):
        pm = ProceduralMemory()
        episodes = [{"content": "run test A"}, {"content": "run test A"}, {"content": "deploy B"}]
        skills = pm.extract_pattern(episodes)
        assert len(skills) >= 1

    def test_execute_found(self):
        pm = ProceduralMemory()
        pm.extract_pattern([{"content": "run test"}, {"content": "run test"}, {"content": "deploy"}])
        sid = list(pm.skills.keys())[0]
        result = pm.execute(sid)
        assert result["ok"]

    def test_execute_not_found(self):
        pm = ProceduralMemory()
        result = pm.execute("nonexistent")
        assert not result["ok"]

    def test_match_trigger(self):
        pm = ProceduralMemory()
        pm.extract_pattern([{"content": "run deployment pipeline"}, {"content": "run deployment pipeline"}, {"content": "other"}])
        skill = pm.match_trigger("run deployment")
        assert skill is not None

    def test_match_trigger_no_match(self):
        pm = ProceduralMemory()
        pm.extract_pattern([{"content": "run test suite"}])
        skill = pm.match_trigger("unrelated query")
        assert skill is None

    def test_skill_count(self):
        pm = ProceduralMemory()
        pm.extract_pattern([{"content": "a"}, {"content": "a"}, {"content": "b"}, {"content": "b"}])
        assert pm.skill_count() == 2

    def test_clear(self):
        pm = ProceduralMemory()
        pm.extract_pattern([{"content": "test"}])
        pm.clear()
        assert pm.skill_count() == 0
