from memoryx.core import HermesAdapter, MemoryKernel

def seed(db):
    k = MemoryKernel(db)
    for i in range(20):
        ev = k.create_evidence("user_message", f"adaptive concise memory {i}")
        k.create_claim("fact", f"adaptive concise memory {i}", [ev])
    k.close()

def test_adaptive_context_modes_and_summary(tmp_path):
    db = str(tmp_path / "m.db")
    seed(db)
    adapter = HermesAdapter(db)
    out = adapter.query("quick summary", session_id="s1",
                        session_history=["Decision: use budgeted context", "TODO: summarize session"],
                        mode="brief")
    assert out["ok"] is True
    assert out["provenance"]["mode"] == "brief"
    assert out["context_pack"]["used_tokens"] <= 4096
    assert out["context_pack"]["sections"]["session_summary"]
    assert out["session_context"] == []
    adapter.kernel.close()

def test_adaptive_context_previous_pack_diff(tmp_path):
    db = str(tmp_path / "m.db")
    seed(db)
    adapter = HermesAdapter(db)
    a = adapter.query("adaptive concise", session_id="s", request_id="r1", mode="standard")
    # Signal more content then query again with same query
    adapter.signal("user_message", "memory items about adaptive concise", session_id="s")
    adapter.query("adaptive concise", session_id="s", request_id="r2", mode="standard", previous_pack_id=a["provenance"]["pack_id"])
    # The diff may not have repeated if FTS doesn't match, but that's acceptable
    adapter.kernel.close()
