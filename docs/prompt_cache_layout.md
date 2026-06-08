# Prompt Cache Friendly Context Layout

Phase 15.7 separates MemoryX context into stable and dynamic blocks.

## Layout

```text
static_prefix
memory_block
dynamic_task_block
dynamic_runtime_block
warning_block
````

## Rule

Do not put `request_id`, query text, timestamps, or dynamic debug metadata into the static prefix.

## Hashes

Each context pack includes:

* static_prefix_hash
* memory_block_hash
* dynamic_block_hash
* full_pack_hash
  """)

write("docs/context_pack_telemetry.md", """

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
