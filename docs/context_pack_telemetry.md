# Context Pack Telemetry

Phase 15.7 records each context pack in:

```text
memoryx_context_pack_telemetry
```

Tracked fields:

* pack_id
* session_id
* request_id
* mode
* used_tokens
* included_items
* dropped_items
* static_prefix_hash
* memory_block_hash
* full_pack_hash
* estimated_cache_hit
* cache_reuse_ratio
* latency_ms

The cache hit value is only an estimate. Actual provider cache behavior depends on provider-specific implementation.
