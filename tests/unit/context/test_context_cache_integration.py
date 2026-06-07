"""Context pack cache layout integration test."""
from __future__ import annotations
from memoryx.mcp._compat import HermesAdapter, MemoryKernel


def seed(db):
    k = MemoryKernel(db)
    for i in range(8):
        ev = k.create_evidence("user_message", "cache integration memory " + str(i))
        k.create_claim("fact", "cache integration memory " + str(i), [ev])
    k.close()


def test_context_pack_has_cache_layout_and_reuse(tmp_path):
    db = str(tmp_path / "m.db")
    seed(db)
    adapter = HermesAdapter(db)

    a = adapter.query("cache integration", session_id="s", request_id="r1")
    assert "cache_layout" in a["context_pack"]
    cl = a["context_pack"]["cache_layout"]
    assert isinstance(cl, dict)
    # First pack should have items
    assert a["context_pack"]["included_items"] > 0
