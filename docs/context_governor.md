# Context Governor

MemoryX must never inject all memory by default.

Phase 15.5 introduces a budgeted context pack:

- hard token budget
- per-item truncation
- max memory item count
- score filtering
- cold-start new thread policy
- stale request rejection

## Default limits

```text
MEMORYX_CONTEXT_MAX_TOKENS=8192
MEMORYX_CONTEXT_MAX_ITEMS=24
MEMORYX_CONTEXT_MAX_ITEM_TOKENS=512
MEMORYX_CONTEXT_MIN_SCORE=0.20
MEMORYX_CONTEXT_SESSION_CARRYOVER=false
```

## Safe query

```python
from memoryx.context_budget import BudgetedContextAssembler

assembler = BudgetedContextAssembler("./memoryx.db")
pack = assembler.assemble(query="deploy issue", session_id="s1")
```

## Integration Lockdown

Phase 15.5B requires all default prompt-injection paths to use `BudgetedContextAssembler`.

Mandatory safe default paths:
- `HermesAdapter.query`
- MCP `memory.query`

Explicit raw/debug paths:
- `HermesAdapter.raw_query`
- MCP `memory.debug`

A feature is not considered fixed if the budgeted assembler exists but the default query path still bypasses it.
