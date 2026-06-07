from memoryx.core.fusion import RankedCandidate, reciprocal_rank_fusion, make_ranked_candidates

def test_rrf_empty():
    assert reciprocal_rank_fusion([]) == {}

def test_rrf_favors_appearing_in_multiple_lists():
    fused = reciprocal_rank_fusion([
        [RankedCandidate("a", 1), RankedCandidate("b", 2)],
        [RankedCandidate("a", 2), RankedCandidate("c", 1)],
    ])
    assert fused["a"] == 1.0
    assert fused["a"] > fused["b"]
    assert fused["a"] > fused["c"]

def test_rrf_ignores_invalid_rank():
    fused = reciprocal_rank_fusion([[RankedCandidate("a", 0), RankedCandidate("b", 1)]])
    assert "a" not in fused
    assert "b" in fused

def test_make_ranked_candidates():
    cands = make_ranked_candidates(["x", "y", "z"], "test")
    assert len(cands) == 3
    assert cands[0].rank == 1
    assert cands[1].rank == 2
    assert all(c.source == "test" for c in cands)
