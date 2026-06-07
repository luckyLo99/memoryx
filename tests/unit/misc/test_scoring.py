from memoryx.core.scoring import (
    access_boost, confidence_label, decay_multiplier, normalize_bm25, status_penalty, compute_final_score,
)

def test_normalize_bm25_bounds():
    assert 0 <= normalize_bm25(-1.0) <= 1
    assert normalize_bm25(0.0) == 1.0

def test_normalize_bm25_none():
    assert normalize_bm25(None) == 0.0

def test_decay_never_zeroes():
    assert decay_multiplier("2000-01-01T00:00:00+00:00", None) >= 0.30

def test_decay_recent_is_higher():
    old = decay_multiplier("2000-01-01T00:00:00+00:00", None)
    new = decay_multiplier("2026-06-03T00:00:00+00:00", None)
    assert new > old

def test_status_penalty_revoked_highest():
    assert status_penalty("revoked") > status_penalty("active")
    assert status_penalty("revoked") > status_penalty("superseded")

def test_access_boost_increases_with_count():
    assert access_boost(10, None) > access_boost(0, None)

def test_confidence_label_segments():
    assert confidence_label(0.8) == "high"
    assert confidence_label(0.5) == "medium"
    assert confidence_label(0.2) == "low"
    assert confidence_label(0.01) == "rejected"

def test_final_score_bounds():
    s = compute_final_score(bm25_score=-0.1, vector_score=None, updated_at=None, last_accessed_at=None, access_count=0, importance=0.5, confidence=0.5, status="active")
    assert 0 <= s.final_score <= 1

def test_final_score_with_rrf():
    s = compute_final_score(bm25_score=None, vector_score=None, updated_at=None, last_accessed_at=None, access_count=0, importance=0.5, confidence=0.5, status="active", rrf_score=0.8)
    assert s.rrf_score == 0.8
    assert 0 <= s.final_score <= 1

def test_final_score_with_vector():
    s = compute_final_score(bm25_score=None, vector_score=0.9, updated_at=None, last_accessed_at=None, access_count=0, importance=0.5, confidence=0.5, status="active")
    assert s.vector_score == 0.9
