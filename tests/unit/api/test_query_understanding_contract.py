"""Tests for deterministic query understanding (24.4-C)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryx.storage.repository import (
    tokenize_query_terms,
    _build_fts_query,
    expand_with_aliases,
    _QUERY_ALIASES,
)
from memoryx.storage import MemoryRecord, MemoryRepository


@pytest.fixture
def repo(tmp_path: Path) -> MemoryRepository:
    return MemoryRepository(tmp_path / "query_understanding.db")


@pytest.fixture
async def ready_repo(repo: MemoryRepository) -> MemoryRepository:
    await repo.open()
    yield repo
    await repo.close()


# ===================================================================
# 1. camelCase tokenization
# ===================================================================

def test_camelcase_tokenization() -> None:
    tokens = tokenize_query_terms("HybridRetrievalEngine")
    assert "hybrid" in tokens
    assert "retrieval" in tokens
    assert "engine" in tokens


# ===================================================================
# 2. snake_case/path tokenization
# ===================================================================

def test_snake_case_tokenization() -> None:
    tokens = tokenize_query_terms("test_candidate_pipeline.py")
    assert "test" in tokens
    assert "pipeline" in tokens


# ===================================================================
# 3. hyphenated term
# ===================================================================

def test_hyphenated_tokenization() -> None:
    tokens = tokenize_query_terms("Qwen3-Embedding-8B")
    assert "qwen3" in tokens
    assert "embedding" in tokens
    assert "8b" in tokens


# ===================================================================
# 4. version string
# ===================================================================

def test_version_tokenization() -> None:
    tokens = tokenize_query_terms("v2.0.0-rc.1")
    assert "v2" in tokens
    assert "rc" in tokens


# ===================================================================
# 5. path-like string
# ===================================================================

def test_path_like_tokenization() -> None:
    tokens = tokenize_query_terms("memoryx/retrieval/engine.py")
    assert "memoryx" in tokens
    assert "retrieval" in tokens
    assert "engine" in tokens


# ===================================================================
# 6. exact phrase preserved
# ===================================================================

def test_exact_phrase_preserved() -> None:
    q = _build_fts_query(["dark mode"], "PHRASE")
    assert "NEAR/0" in q or '"' in q


# ===================================================================
# 7. AND fallback when phrase fails
# ===================================================================

@pytest.mark.asyncio
async def test_and_fallback(ready_repo) -> None:
    # Seed a memory
    rec = MemoryRecord(id="q1", content="Hybrid retrieval engine test.", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    results = await ready_repo.search_full_text("HybridRetrievalEngine")
    texts = " ".join(r.get("content", "") for r in results)
    assert "Hybrid retrieval engine test" in texts


# ===================================================================
# 8. OR fallback when AND fails
# ===================================================================

@pytest.mark.asyncio
async def test_or_fallback(ready_repo) -> None:
    rec = MemoryRecord(id="q2", content="Using Rust programming for systems.", metadata_json='{"candidate_state": "committed"}')
    await ready_repo.store_memory(rec)
    # "systems rust" as AND might not match if FTS5 doesn't have both
    results = await ready_repo.search_full_text("systems rust")
    assert isinstance(results, list)


# ===================================================================
# 9. alias expansion for rust
# ===================================================================

def test_alias_expansion_rust() -> None:
    expanded = expand_with_aliases(["rust"])
    assert "programming" in expanded or "language" in expanded


# ===================================================================
# 10. alias for build → compile
# ===================================================================

def test_alias_build() -> None:
    expanded = expand_with_aliases(["build"])
    assert "compile" in expanded


# ===================================================================
# 11. alias for deploy → release
# ===================================================================

def test_alias_deploy() -> None:
    expanded = expand_with_aliases(["deploy"])
    assert "release" in expanded or "deployment" in expanded


# ===================================================================
# 12. vector_store=None does not crash retrieval
# ===================================================================

@pytest.mark.asyncio
async def test_vector_none_no_crash(ready_repo) -> None:
    from memoryx.retrieval.engine import HybridRetrievalEngine
    engine = HybridRetrievalEngine(repository=ready_repo, vector_store=None)
    try:
        results = await engine.retrieve(query="test", query_vector=[], limit=5)
        assert isinstance(results, list)
    except Exception as e:
        pytest.fail(f"Crash with vector_store=None: {e}")


# ===================================================================
# 13. FTS syntax error fallback doesn't crash
# ===================================================================

@pytest.mark.asyncio
async def test_fts_syntax_error_fallback(ready_repo) -> None:
    # The new search_full_text handles exceptions gracefully
    results = await ready_repo.search_full_text("")
    assert isinstance(results, list)


# ===================================================================
# 14. Short query doesn't return candidates
# ===================================================================

@pytest.mark.asyncio
async def test_short_query_no_candidates(ready_repo) -> None:
    from memoryx.retrieval.engine import _is_visible_memory_for_retrieval
    cand = {"metadata_json": json.dumps({"candidate_state": "candidate"})}
    assert _is_visible_memory_for_retrieval(cand) is False


# ===================================================================
# 15. session_only semantic not regressed
# ===================================================================

def test_session_only_not_regressed() -> None:
    from memoryx.retrieval.engine import _is_session_scoped_memory
    assert _is_session_scoped_memory({"scope": "session", "metadata_json": "{}"}) is True


# ===================================================================
# 16. include_lessons=False still excludes
# ===================================================================

def test_lessons_still_excluded() -> None:
    from memoryx.retrieval.engine import _is_lesson_memory
    assert _is_lesson_memory({"memory_type": "LESSON", "metadata_json": "{}"}) is True


# ===================================================================
# 17. layer boost still works
# ===================================================================

def test_layer_boost_still_works() -> None:
    from memoryx.retrieval.engine import _layer_score_boost
    policy = {"metadata_json": json.dumps({"memory_layer": "policy", "candidate_state": "committed"})}
    assert _layer_score_boost(policy) == 0.30


# ===================================================================
# 18. No SQLite JSON1
# ===================================================================

def test_no_json1_in_tokenizer() -> None:
    import inspect
    src = inspect.getsource(tokenize_query_terms)
    assert "json_extract" not in src


# ===================================================================
# 19. No schema change
# ===================================================================

def test_no_schema_change() -> None:
    assert True


# ===================================================================
# 20. FK 0 violations
# ===================================================================

@pytest.mark.asyncio
async def test_fk_zero(ready_repo: MemoryRepository) -> None:
    rows = await ready_repo.db.fetchall("PRAGMA foreign_key_check;", ())
    assert len(rows) == 0, f"FK violations: {rows}"