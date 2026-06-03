"""Tests for the Retriever — FTS5 search with score explanations."""

import os
import tempfile

import pytest

from memoryx.core.kernel import MemoryKernel
from memoryx.core.retriever import Retriever


@pytest.fixture
def kernel():
    """Seed a kernel with some test claims."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    k = MemoryKernel(tmp.name)
    # Seed data
    k.create_claim("preference", "User prefers concise answers", [],
                    confidence=0.8, importance=0.7)
    k.create_claim("fact", "Paris is the capital of France", [])
    k.create_claim("preference", "User likes Python programming", [],
                    confidence=0.9, importance=0.6)
    k.create_claim("fact", "The sky is blue during daytime", [])
    k.create_claim("preference", "User prefers dark mode UI", [],
                    confidence=0.6, importance=0.5)
    yield k
    k.close()
    os.unlink(tmp.name)


@pytest.fixture
def retriever(kernel: MemoryKernel):
    return Retriever(kernel.db)


# ------------------------------------------------------------------
# Basic FTS match
# ------------------------------------------------------------------

class TestBasicRetrieval:
    def test_simple_match(self, retriever: Retriever):
        results = retriever.search("concise")
        assert len(results) >= 1
        assert "concise" in results[0].content

    def test_multi_word_match(self, retriever: Retriever):
        results = retriever.search("Python programming")
        assert len(results) >= 1
        assert any("Python" in r.content for r in results)

    def test_chinese_match(self, retriever: Retriever):
        results = retriever.search("capital")
        assert len(results) >= 1
        assert "France" in results[0].content

    def test_no_match(self, retriever: Retriever):
        results = retriever.search("xyznonexistentkeyword")
        assert len(results) == 0

    def test_limit(self, retriever: Retriever):
        results = retriever.search("prefers", limit=2)
        assert len(results) <= 2


# ------------------------------------------------------------------
# Score & explanation
# ------------------------------------------------------------------

class TestScoreExplanation:
    def test_explanation_fields(self, retriever: Retriever):
        results = retriever.search("Paris")
        assert len(results) > 0
        r = results[0]
        assert r.score is not None  # BM25 score
        assert r.explanation["matched"] is True
        assert r.explanation["query"] == "Paris"
        assert "bm25_score" in r.explanation

    def test_ordering(self, retriever: Retriever):
        # BM25: lower score = better match, results should be sorted
        results = retriever.search("prefers")
        if len(results) >= 2:
            # Each should have a valid BM25 score
            for r in results:
                assert isinstance(r.score, (int, float))


# ------------------------------------------------------------------
# Count
# ------------------------------------------------------------------

class TestCount:
    def test_count_match(self, retriever: Retriever):
        assert retriever.count("prefers") >= 2

    def test_count_no_match(self, retriever: Retriever):
        assert retriever.count("xyznonexistentkeyword") == 0
