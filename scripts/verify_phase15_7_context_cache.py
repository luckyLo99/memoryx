from __future__ import annotations

from pathlib import Path
import tempfile

from memoryx.context_budget import ContextPackTelemetryStore, PromptCacheLayoutBuilder
from memoryx.core import HermesAdapter, MemoryKernel


def seed(db: str):
    k = MemoryKernel(db)
    for i in range(12):
        ev = k.create_evidence("user_message", f"cache friendly memory {i} deploy context")
        k.create_claim("fact", f"cache friendly memory {i} deploy context", [ev], confidence=0.8, importance=0.7)
    k.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "cache_context.db")
        seed(db)

        adapter = HermesAdapter(db)
        first = adapter.query("deploy context", session_id="s1", request_id="r1", mode="standard")
        assert first["ok"] is True
        pack1 = first["context_pack"]
        assert "cache_layout" in pack1
        assert "cache_reuse" in pack1
        assert pack1["cache_reuse"]["estimated_cache_hit"] is False

        second = adapter.query("deploy context updated", session_id="s1", request_id="r2", mode="standard")
        pack2 = second["context_pack"]
        assert pack2["cache_reuse"]["estimated_cache_hit"] is True
        assert pack2["cache_reuse"]["cache_reuse_ratio"] >= 0.35
        assert pack1["cache_layout"]["static_prefix_hash"] == pack2["cache_layout"]["static_prefix_hash"]

        third = adapter.query("deploy context updated", session_id="s1", request_id="r3", mode="standard")
        pack3 = third["context_pack"]
        assert pack3["cache_reuse"]["cache_reuse_ratio"] >= 0.35

        telemetry = ContextPackTelemetryStore(db).last_for_session("s1")
        assert telemetry is not None
        assert telemetry["pack_id"] == third["provenance"]["pack_id"]
        assert telemetry["used_tokens"] > 0

        assert "Dynamic Task Block" in pack2["cache_layout"]["rendered_text"]
        assert "Reusable Memory Block" in pack2["cache_layout"]["rendered_text"]

        adapter.kernel.close()

    print("PASS Phase 15.7 context cache verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
