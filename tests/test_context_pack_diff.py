from memoryx.context_budget import ContextPackHistory
from memoryx.core import MemoryKernel

def test_context_pack_history_diff(tmp_path):
    db = str(tmp_path / "m.db")
    MemoryKernel(db).close()
    h = ContextPackHistory(db)
    h.record_pack(pack_id="p1", session_id="s", request_id="r1", query="q", item_ids=["a", "b"], used_tokens=10)
    d = h.diff("p1", ["b", "c"], "p2")
    assert d.repeated_item_ids == ["b"]
    assert d.new_item_ids == ["c"]
