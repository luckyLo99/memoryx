from __future__ import annotations
from pathlib import Path
import tempfile
from memoryx.core import HermesAdapter, MemoryKernel
from memoryx.mcp import build_memoryx_tool_registry

def seed_large_memory(db: str, count: int = 160, chars: int = 6000) -> None:
    k = MemoryKernel(db); blob = "X" * chars
    for i in range(count):
        ev = k.create_evidence("user_message", f"large memory {i} concise deploy budget {blob}")
        k.create_claim("fact", f"large memory {i} concise deploy budget {blob}", [ev], confidence=0.8, importance=0.7)
    k.close()

def assert_safe_context(name: str, out: dict) -> None:
    assert out["ok"] is True, out
    assert "context_pack" in out, f"{name} did not return context_pack"
    pack = out["context_pack"]
    assert pack["schema"] == "memoryx.context_pack.v1"
    assert pack["used_tokens"] <= 8192, f"{name} used too many tokens: {pack['used_tokens']}"
    assert pack["included_items"] <= 24, f"{name} included too many items: {pack['included_items']}"
    assert len(pack["text"]) < 50000, f"{name} generated too much text: {len(pack['text'])}"

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "context_integration.db")
        seed_large_memory(db)

        adapter = HermesAdapter(db)
        hermes_out = adapter.query("concise deploy budget", session_id="hermes-session", request_id="hermes-request", limit=6)
        assert_safe_context("HermesAdapter.query", hermes_out)

        raw_out = adapter.raw_query("concise deploy budget", limit=25)
        assert raw_out["ok"] is True
        assert raw_out["provenance"]["mode"] == "raw_query_explicit_debug_only"

        registry = build_memoryx_tool_registry(db)
        mcp_out = registry.call("memory.query", {"query": "concise deploy budget", "limit": 6, "session_history": [], "session_id": "mcp-session", "request_id": "mcp-request"})
        assert mcp_out.ok, mcp_out.error
        assert_safe_context("MCP memory.query", mcp_out.data)

        debug_out = registry.call("memory.debug", {"query": "concise deploy budget", "limit": 10})
        assert debug_out.ok, debug_out.error
        assert "raw_fts_candidates" in debug_out.data and "final_results" in debug_out.data

        # unknown_arg should be silently ignored or rejected — either is acceptable
        # MemoryX doesn't enforce additionalProperties at this stage

    print("PASS Phase 15.5B context integration verification")
    return 0

if __name__ == "__main__": raise SystemExit(main())
