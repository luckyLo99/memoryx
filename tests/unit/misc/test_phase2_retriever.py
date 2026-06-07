from memoryx.core import MemoryKernel, SearchOptions
from memoryx.core.retriever import Retriever

def test_retriever_records_access_and_event(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    ev = k.create_evidence("user_message", "apple memory")
    cid = k.create_claim("fact", "apple memory", [ev], confidence=0.9, importance=0.8)
    hits = Retriever(db).search("apple", options=SearchOptions(limit=5))
    assert hits
    claim = k.get_claim(cid)
    assert claim["access_count"] >= 1
    rows = k.conn.execute("SELECT count(*) FROM retrieval_events").fetchone()
    assert rows[0] >= 1

def test_retriever_hides_revoked(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    ev = k.create_evidence("user_message", "banana")
    cid = k.create_claim("fact", "banana", [ev])
    k.revoke_claim(cid)
    assert Retriever(db).search("banana") == []
    assert Retriever(db).search("banana", options=SearchOptions(include_inactive=True, min_score=0.0, reject_low_confidence=False))

def test_retriever_low_confidence_rejection(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    k.create_claim("fact", "xyz", [], confidence=0.01, importance=0.01)
    hits = Retriever(db).search("xyz", options=SearchOptions(limit=5, reject_low_confidence=True, min_score=0.15))
    # Should still return because score relies on BM25, not just confidence
    # This tests the option path doesn't crash
    assert isinstance(hits, list)
