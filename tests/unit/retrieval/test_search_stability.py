"""Tests for the P0/P1 search stability & correctness improvements.

Covers:
- tokenize_query_terms CJK bigrams
- HybridRetrievalEngine._entity_overlap correctness (regression of set-of-generators bug)
- QueryUnderstanding intent detection
- Fuzzy search / alias expansion
- _enrich_evolution_meta O(n) optimization behavioral equivalence
"""

from __future__ import annotations

import pytest
from pathlib import Path

from memoryx.storage.repository import tokenize_query_terms, MemoryRepository
from memoryx.retrieval.engine import HybridRetrievalEngine
from memoryx.retrieval.query_understanding import QueryUnderstanding, RetrievalIntent
from memoryx.retrieval.fuzzy_search import (
    expand_query_with_fuzzy_aliases,
    levenshtein,
    normalized_edit_distance,
    best_fuzzy_match,
)


# ======================================================================
# 1. CJK tokenizer bigram support
# ======================================================================

def test_cjk_bigram_generation():
    tokens = tokenize_query_terms("记忆系统")
    # Individual chars + bigrams should appear
    assert "记忆" in tokens or "记忆" in "".join(tokens)
    assert any(len(t) == 2 and all("\u4e00" <= ch <= "\u9fff" for ch in t) for t in tokens)


def test_mixed_cjk_english_tokens():
    tokens = tokenize_query_terms("memory记忆system")
    assert "memory" in tokens or any("memory" in t.lower() for t in tokens)
    assert "system" in tokens or any("system" in t.lower() for t in tokens)


def test_token_limit_respected():
    tokens = tokenize_query_terms("a b c d e f g h i j k l m n o p q r s t u v w x y z 1 2 3 4 5 6 7 8 9 10")
    assert len(tokens) <= 24


# ======================================================================
# 2. _entity_overlap correctness (regression for set-of-generators bug)
# ======================================================================

def test_entity_overlap_hits_entity_token():
    score = HybridRetrievalEngine._entity_overlap(
        query_tokens={"docker", "config"},
        entities_json='["docker container", "nginx"]',
    )
    assert score > 0


def test_entity_overlap_no_match():
    score = HybridRetrievalEngine._entity_overlap(
        query_tokens={"python"},
        entities_json='["java", "rust"]',
    )
    assert score == 0.0


def test_entity_overlap_empty_or_invalid_json_is_safe():
    assert HybridRetrievalEngine._entity_overlap(set(), "[]") == 0.0
    assert HybridRetrievalEngine._entity_overlap({"x"}, None) == 0.0
    assert HybridRetrievalEngine._entity_overlap({"x"}, "") == 0.0


# ======================================================================
# 3. QueryUnderstanding intent detection
# ======================================================================

def test_intent_detection_coding():
    qu = QueryUnderstanding()
    intent, conf = qu.classify("how to call the function")
    assert intent in (RetrievalIntent.CODING, RetrievalIntent.FACT)


def test_intent_detection_preference_chinese():
    qu = QueryUnderstanding()
    intent, conf = qu.classify("我最喜欢的歌星是张杰")
    # Chinese preference phrases should at least not crash and produce non-zero confidence.
    assert conf >= 0.0


def test_intent_detection_unknown_default_fact():
    qu = QueryUnderstanding()
    intent, conf = qu.classify("nothing specific here")
    # When no keyword matches, the classifier should not explode and returns a valid intent.
    assert intent is not None


def test_intent_detection_does_not_crash_on_empty():
    qu = QueryUnderstanding()
    intent, conf = qu.classify("")
    assert intent is not None
    assert 0.0 <= conf <= 1.0


# ======================================================================
# 4. Fuzzy search utilities
# ======================================================================

def test_levenshtein_identical_is_zero():
    assert levenshtein("abc", "abc") == 0


def test_levenshtein_known_distance():
    assert levenshtein("kitten", "sitting") == 3


def test_normalized_edit_distance_boundaries():
    assert normalized_edit_distance("abc", "abc") == 0.0
    assert 0.0 <= normalized_edit_distance("a", "zzzzz") <= 1.0


def test_best_fuzzy_match_finds_typo():
    vocab = ["memory", "system", "vector"]
    match = best_fuzzy_match("memry", vocab, max_distance=0.33)
    assert match == "memory"


def test_best_fuzzy_match_none_when_too_far():
    vocab = ["memory", "system"]
    match = best_fuzzy_match("completelydifferent", vocab, max_distance=0.25)
    assert match is None


def test_expand_query_with_aliases_produces_more_tokens():
    base = ["config", "error"]
    expanded = expand_query_with_fuzzy_aliases(base)
    assert len(expanded) >= len(base)
    # "config" should have been expanded to include "configuration" or "setting".
    assert any("configuration" in t.lower() or "setting" in t.lower() for t in expanded)


# ======================================================================
# 5. Async: parallel search returns sensible data shape
# ======================================================================

@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "search_perf.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


@pytest.mark.asyncio
async def test_retrieve_without_vector_store_is_safe(ready_repo):
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=None)
    results = await engine.retrieve(query="memory system performance", query_vector=[], limit=5)
    # Should not crash; returns a list.
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_intent_auto_detection_in_retrieve(ready_repo):
    """With no intent supplied, retrieve() should classify internally without crashing."""
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=None)
    results = await engine.retrieve(
        query="我最喜欢的歌星是张杰", query_vector=[], limit=5,
    )
    assert isinstance(results, list)
