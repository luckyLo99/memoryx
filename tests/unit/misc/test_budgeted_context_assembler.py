from memoryx.context_budget import BudgetedContextAssembler, ContextBudgetPolicy
from memoryx.core import MemoryKernel

def test_budgeted_assembler_does_not_dump_all_memory(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    for i in range(50):
        ev = k.create_evidence("user_message", f"concise memory {i} " + "x" * 2000)
        k.create_claim("fact", f"concise memory {i} " + "x" * 2000, [ev], confidence=0.8, importance=0.8)
    k.close()
    policy = ContextBudgetPolicy(max_context_tokens=2048, max_memory_items=8, max_item_tokens=128)
    out = BudgetedContextAssembler(db, policy=policy).assemble(query="concise", session_id="s1")
    assert out["ok"] is True
    assert out["context_pack"]["used_tokens"] <= 2048
    assert out["context_pack"]["included_items"] <= 8
    assert out["context_pack"]["dropped_items"] > 0
