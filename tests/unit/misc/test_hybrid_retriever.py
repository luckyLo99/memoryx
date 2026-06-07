from memoryx.core import MemoryKernel, SearchOptions
from memoryx.core.hybrid_retriever import HybridRetriever
from memoryx.core.vector import NullVectorProvider, VectorHit

class FakeVectorProvider:
    available = True
    def __init__(self, hits): self.hits = hits
    def search(self, query, limit=20): return self.hits[:limit]
    def upsert(self, claim_id, content): pass
    def delete(self, claim_id): pass

def test_auto_falls_back_to_lite(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    cid = k.create_claim("fact", "orange memory", [k.create_evidence("user_message", "o")])
    hits = HybridRetriever(db, NullVectorProvider()).search("orange", options=SearchOptions(mode="auto"))
    assert hits
    assert hits[0].claim_id == cid

def test_hybrid_uses_rrf(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    cid = k.create_claim("fact", "semantic memory", [k.create_evidence("user_message", "s")])
    provider = FakeVectorProvider([VectorHit(cid, 0.95)])
    hits = HybridRetriever(db, provider).search("different words", options=SearchOptions(mode="hybrid", min_score=0.0))
    assert hits
    assert hits[0].claim_id == cid
    assert hits[0].explanation["fusion"]["method"] == "rrf"

def test_vector_unavailable_vector_mode_returns_empty(tmp_path):
    db = str(tmp_path / "m.db")
    hits = HybridRetriever(db, NullVectorProvider()).search("anything", options=SearchOptions(mode="vector"))
    assert hits == []
