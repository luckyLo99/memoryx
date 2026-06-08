# Context Budget Policy

## Why

Without a context governor, MemoryX can inject hundreds of thousands of tokens into every request. This causes:

- multi-minute response latency
- model context overflow
- 256k-window models failing
- stale results from previous interrupted requests

## Policy

MemoryX defaults to a compact context pack. Raw/debug context remains available through explicit debug tools only.

## Environment variables

```bash
export MEMORYX_CONTEXT_MODE=budgeted
export MEMORYX_MODEL_CONTEXT_TOKENS=256000
export MEMORYX_CONTEXT_MAX_TOKENS=8192
export MEMORYX_CONTEXT_MAX_RATIO=0.04
export MEMORYX_CONTEXT_MAX_ITEMS=24
export MEMORYX_CONTEXT_MAX_ITEM_TOKENS=512
export MEMORYX_CONTEXT_SESSION_CARRYOVER=false
export MEMORYX_REQUEST_STALE_ACTION=reject
```
