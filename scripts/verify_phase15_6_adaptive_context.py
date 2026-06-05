from __future__ import annotations
from pathlib import Path
import tempfile
from memoryx.core import HermesAdapter, MemoryKernel
from memoryx.mcp import build_memoryx_tool_registry
from memoryx.context_budget import AdaptiveContextPlanner, SessionSummaryStore

def seed(db, n=80):
    k = MemoryKernel(db); blob = "Z" * 3000
    for i in range(n):
        ev = k.create_evidence("user_message", f"adaptive memory {i} deploy migration phase patch {blob}")
        k.create_claim("fact", f"adaptive memory {i} deploy migration phase patch {blob}", [ev], confidence=0.8, importance=0.7)
    k.close()

def main():
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "adaptive.db")
        seed(db)

        # Planner
        planner = AdaptiveContextPlanner(model_window_tokens=256000)
        brief = planner.plan("quick summary")
        deep = planner.plan("phase migration architecture patch implementation")
        debug = planner.plan("full debug diagnostics raw_fts")
        assert brief.mode == "brief"
        assert deep.mode == "deep"
        assert debug.mode == "debug"
        assert brief.policy.max_context_tokens < deep.policy.max_context_tokens <= debug.policy.max_context_tokens

        # Adapter with modes + summary + diff
        adapter = HermesAdapter(db)
        history = ["User asked to fix context overflow.", "Decision: default query must be budgeted.", "TODO: add summarized session carryover.", "Patch should avoid raw history injection."]

        out1 = adapter.query("phase migration architecture patch implementation", session_id="s1", request_id="r1",
                             session_history=history, mode="deep")
        assert out1["ok"] is True
        assert out1["provenance"]["mode"] == "deep"
        assert out1["context_pack"]["used_tokens"] <= 16384
        assert out1["context_pack"]["sections"]["session_summary"]
        assert out1["session_context"] == []
        assert out1["provenance"]["budget_policy"]["session_history_injected_raw"] is False

        pack_id = out1["provenance"]["pack_id"]

        # Simple FTS-safe query for diff test
        adapter.signal("user_message", "deploy memory items for testing budget", session_id="s1")
        out2 = adapter.query("deploy memory", session_id="s1",
                             request_id="r2", session_history=history, mode="deep", previous_pack_id=pack_id)
        assert out2["ok"] is True
        assert out2["context_pack"]["included_items"] >= 1
        print(f"  pack2: included={out2['context_pack']['included_items']}, diff={out2['context_pack']['diff']}")


        # Summary store
        summary = SessionSummaryStore(db).get("s1")
        assert summary is not None
        assert "Session summary" in summary.summary

        # MCP adaptive
        reg = build_memoryx_tool_registry(db)
        mcp = reg.call("memory.query", {"query": "quick summary", "mode": "brief", "session_id": "mcp-s1", "session_history": ["TODO: keep context small"]})
        assert mcp.ok, mcp.error
        assert mcp.data["provenance"]["mode"] == "brief"
        assert mcp.data["context_pack"]["used_tokens"] <= 4096

        adapter.kernel.close()

    print("PASS Phase 15.6 adaptive context verification")
    return 0

if __name__ == "__main__": raise SystemExit(main())
