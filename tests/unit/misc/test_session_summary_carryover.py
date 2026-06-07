from memoryx.context_budget import SessionSummaryStore
from memoryx.core import MemoryKernel

def test_session_summary_store(tmp_path):
    db = str(tmp_path / "m.db")
    MemoryKernel(db).close()
    store = SessionSummaryStore(db)
    s = store.upsert_from_history("s1", ["hello", "TODO: fix context", "last turn"])
    assert s.session_id == "s1"
    assert "TODO" in s.summary or "fix context" in s.summary
    again = store.get("s1")
    assert again is not None
    assert again.source_hash == s.source_hash
