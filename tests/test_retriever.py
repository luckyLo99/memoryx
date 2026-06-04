"""Phase 1 retriever tests — FTS5 search with status awareness.

Aligns with Phase 1 specification.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from memoryx.core import MemoryKernel, Retriever, SearchOptions


@pytest.fixture
def retriever() -> Retriever:
    db = str(Path(tempfile.mktemp(suffix=".db")))
    k = MemoryKernel(db)
    # Seed data
    k.create_claim("preference", "User prefers concise answers", [],
                    confidence=0.8, importance=0.7)
    k.create_claim("fact", "Paris is the capital of France", [])
    k.create_claim("preference", "User likes Python programming", [],
                    confidence=0.9, importance=0.6)
    k.create_claim("fact", "The sky is blue during daytime", [])
    k.create_claim("preference", "User prefers dark mode UI", [],
                    confidence=0.6, importance=0.5)

    r = Retriever(db)
    yield r
    k.close()
    Path(db).unlink(missing_ok=True)


# ------------------------------------------------------------------
# test_retriever_finds_active_claim
# ------------------------------------------------------------------

def test_retriever_finds_active_claim() -> None:
    db = str(Path(tempfile.mktemp(suffix=".db")))
    kernel = MemoryKernel(db)

    ev = kernel.create_evidence("user_message", "I like apples")
    cid = kernel.create_claim("preference", "I like apples", [ev])

    results = Retriever(db).search("apples")
    assert len(results) == 1
    assert results[0].claim_id == cid
    assert "bm25_score" in results[0].explanation
    assert "lexical_score" in results[0].explanation

    kernel.close()
    Path(db).unlink(missing_ok=True)


# ------------------------------------------------------------------
# test_retriever_hides_revoked_by_default
# ------------------------------------------------------------------

def test_retriever_hides_revoked_by_default() -> None:
    db = str(Path(tempfile.mktemp(suffix=".db")))
    kernel = MemoryKernel(db)

    ev = kernel.create_evidence("user_message", "secret apple")
    cid = kernel.create_claim("fact", "secret apple", [ev])
    kernel.revoke_claim(cid)

    r = Retriever(db)
    # Default (include_inactive=False) → revoked hidden
    assert r.search("apple") == []
    # Explicit include_inactive → visible
    assert len(r.search("apple", options=SearchOptions(include_inactive=True, min_score=0.0, reject_low_confidence=False))) == 1
    assert r.search("apple", options=SearchOptions(include_inactive=True, min_score=0.0, reject_low_confidence=False))[0].claim_id == cid

    kernel.close()
    Path(db).unlink(missing_ok=True)


# ------------------------------------------------------------------
# test_retriever_limit
# ------------------------------------------------------------------

def test_retriever_limit() -> None:
    db = str(Path(tempfile.mktemp(suffix=".db")))
    kernel = MemoryKernel(db)

    for i in range(5):
        kernel.create_claim("fact", f"apple item {i}", [])

    results = Retriever(db).search("apple", limit=2)
    assert len(results) == 2

    kernel.close()
    Path(db).unlink(missing_ok=True)