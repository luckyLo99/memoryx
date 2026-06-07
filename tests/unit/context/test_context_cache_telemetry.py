from memoryx.context_budget import ContextPackTelemetryStore, ContextTelemetryRecord
from memoryx.core import MemoryKernel


def test_telemetry_reuse_estimate(tmp_path):
    db = str(tmp_path / "m.db")
    MemoryKernel(db).close()
    store = ContextPackTelemetryStore(db)

    first = store.estimate_reuse(session_id="s", static_prefix_hash="a", memory_block_hash="b", dynamic_block_hash="c")
    assert first["estimated_cache_hit"] is False

    store.record(ContextTelemetryRecord(
        pack_id="p1",
        session_id="s",
        request_id="r1",
        mode="standard",
        used_tokens=100,
        included_items=1,
        dropped_items=0,
        static_prefix_hash="a",
        memory_block_hash="b",
        dynamic_block_hash="c",
        full_pack_hash="abc",
        estimated_cache_hit=False,
        cache_reuse_ratio=0.0,
        latency_ms=1.0,
    ))

    second = store.estimate_reuse(session_id="s", static_prefix_hash="a", memory_block_hash="b", dynamic_block_hash="d")
    assert second["estimated_cache_hit"] is True
    assert second["cache_reuse_ratio"] >= 0.8
