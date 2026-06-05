from __future__ import annotations
from pathlib import Path
import tempfile
from memoryx.context_budget import ActiveRequestStore, BudgetedContextAssembler, ContextBudgetPolicy
from memoryx.core import MemoryKernel

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "context_governor.db")
        kernel = MemoryKernel(db)
        # 120 long items
        for i in range(120):
            ev = kernel.create_evidence("user_message", f"memory {i} concise deploy " + "X" * 8000)
            kernel.create_claim("fact", f"memory {i} concise deploy " + "X" * 8000, [ev], confidence=0.8, importance=0.7)
        kernel.close()

        policy = ContextBudgetPolicy(max_context_tokens=4096, max_memory_items=12, max_item_tokens=128)
        assembler = BudgetedContextAssembler(db, policy=policy)
        out = assembler.assemble(query="concise deploy", session_id="s1", request_id="r1")
        assert out["ok"] is True
        pack = out["context_pack"]
        assert pack["used_tokens"] <= 4096, f"used {pack['used_tokens']} > 4096"
        assert pack["included_items"] <= 12, f"included {pack['included_items']} > 12"
        assert pack["dropped_items"] > 0, "should have dropped items"
        print(f"Budget OK: used={pack['used_tokens']}t, included={pack['included_items']}, dropped={pack['dropped_items']}")

        # Stale request guard
        guard = ActiveRequestStore(db)
        guard.begin_request(session_id="same-session", task_text="old task", request_id="old")
        guard.begin_request(session_id="same-session", task_text="new task", request_id="new")
        assert guard.reject_if_stale("old", "same-session")["error"] == "stale_result"
        assert guard.reject_if_stale("new", "same-session") is None
        print("Stale guard: PASS")
        
    print("PASS Phase 15.5 context governor verification")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
