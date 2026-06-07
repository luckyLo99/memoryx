from memoryx.core import HermesAdapter, MemoryKernel
from memoryx.mcp import build_memoryx_tool_registry

def seed(db: str, n: int = 80):
    k = MemoryKernel(db); blob = "Y" * 5000
    for i in range(n):
        ev = k.create_evidence("user_message", f"integration memory {i} budget concise {blob}")
        k.create_claim("fact", f"integration memory {i} budget concise {blob}", [ev], confidence=0.8, importance=0.7)
    k.close()

def assert_budgeted(out: dict):
    assert out["ok"] is True
    assert "context_pack" in out
    assert out["context_pack"]["used_tokens"] <= 8192
    assert out["context_pack"]["included_items"] <= 24
    assert len(out["context_pack"]["text"]) < 40000

def test_hermes_query_uses_budgeted_context(tmp_path):
    db = str(tmp_path / "m.db"); seed(db)
    adapter = HermesAdapter(db)
    out = adapter.query("budget concise", session_id="s1", request_id="r1")
    assert_budgeted(out)
    raw = adapter.raw_query("budget concise", limit=20)
    assert raw["ok"] is True and raw["provenance"]["mode"] == "raw_query_explicit_debug_only"
    adapter.kernel.close()

def test_mcp_memory_query_uses_budgeted_context(tmp_path):
    db = str(tmp_path / "m.db"); seed(db)
    reg = build_memoryx_tool_registry(db)
    result = reg.call("memory.query", {"query": "budget concise", "limit": 6, "session_history": [], "session_id": "mcp-s1", "request_id": "mcp-r1"})
    assert result.ok, result.error
    assert_budgeted(result.data)

def test_mcp_memory_debug_is_explicit_raw_debug_path(tmp_path):
    db = str(tmp_path / "m.db"); seed(db)
    reg = build_memoryx_tool_registry(db)
    result = reg.call("memory.debug", {"query": "budget concise", "limit": 10})
    assert result.ok, result.error
    assert "raw_fts_candidates" in result.data and "final_results" in result.data

def test_mcp_memory_query_tolerates_unknown_args(tmp_path):
    db = str(tmp_path / "m.db"); seed(db, n=1)
    reg = build_memoryx_tool_registry(db)
    result = reg.call("memory.query", {"query": "budget", "unknown_arg": "nope"})
    assert result.ok  # unknown args are silently accepted — no validation rejection at this stage
