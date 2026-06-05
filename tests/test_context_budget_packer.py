from memoryx.context_budget import ContextBudgetPolicy, ContextItem, ContextPacker

def test_context_packer_enforces_budget():
    policy = ContextBudgetPolicy(max_context_tokens=512, max_memory_items=3, max_item_tokens=64)
    packer = ContextPacker(policy)
    items = [ContextItem(str(i), "relevant_memories", "deploy memory " + ("x" * 1000), score=1.0 - i * 0.01) for i in range(20)]
    pack = packer.pack(request_id="r", session_id="s", query="deploy", items=items)
    assert pack.used_tokens <= 512
    assert pack.included_items <= 3
    assert pack.dropped_items > 0
