from memoryx.core import MemoryKernel
from memoryx.mcp import build_memoryx_tool_registry

def test_mcp_adaptive_query_mode(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    ev = k.create_evidence("user_message", "mcp adaptive context memory")
    k.create_claim("fact", "mcp adaptive context memory", [ev])
    k.close()

    reg = build_memoryx_tool_registry(db)
    result = reg.call("memory.query", {"query": "quick summary", "mode": "brief",
        "session_history": ["TODO: keep context small"], "session_id": "s1"})
    assert result.ok, result.error
    assert result.data["provenance"]["mode"] == "brief"
    assert result.data["context_pack"]["used_tokens"] <= 4096
