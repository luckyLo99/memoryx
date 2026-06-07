from memoryx.core import HermesAdapter, MemoryKernel


def seed(db):
    k = MemoryKernel(db)
    for i in range(8):
        ev = k.create_evidence("user_message", f"cache integration memory {i}")
        k.create_claim("fact", f"cache integration memory {i}", [ev])
    k.close()


def test_context_pack_has_cache_layout_and_reuse(tmp_path):
    db = str(tmp_path / "m.db")
    seed(db)
    adapter = HermesAdapter(db)

    a = adapter.query("cache integration", session_id="s", request_id="r1")
    b = adapter.query("cache integration changed", session_id="s", request_id="r2")

    assert "cache_layout" in a["context_pack"]
    assert "cache_reuse" in b["context_pack"]
    assert b["context_pack"]["cache_reuse"]["estimated_cache_hit"] is True
    assert b["provenance"]["cache_layout"]["cache_reuse_ratio"] >= 0.35
    adapter.kernel.close()
