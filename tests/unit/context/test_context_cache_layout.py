from memoryx.context_budget import PromptCacheLayoutBuilder


def test_layout_hash_stable_for_same_memory_different_request():
    pack = {
        "schema": "memoryx.context_pack.v1",
        "mode": "standard",
        "request_id": "r1",
        "session_id": "s",
        "pack_id": "p1",
        "query": "hello",
        "used_tokens": 10,
        "included_items": 1,
        "dropped_items": 0,
        "warnings": [],
        "sections": {
            "session_summary": [],
            "relevant_memories": [{"id": "m1", "score": 0.9, "content": "memory", "type": "fact"}],
        },
    }
    b = PromptCacheLayoutBuilder()
    a = b.build(pack)
    pack["request_id"] = "r2"
    pack["query"] = "changed"
    c = b.build(pack)
    assert a.static_prefix_hash == c.static_prefix_hash
    assert a.memory_block_hash == c.memory_block_hash
    assert a.dynamic_block_hash != c.dynamic_block_hash
