# Summarized Session Carryover

Phase 15.6 replaces raw session history injection with compact summaries.

## Why

Raw session history can accidentally reintroduce huge prompts. MemoryX now stores:

```text
memoryx_session_summaries
```

Each summary is deterministic and Lite-safe.

## Behavior

* Same session may inject a compact summary.
* New thread still defaults to cold start.
* `session_context` remains empty by default.
* Raw history is never injected directly into prompt context.
