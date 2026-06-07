# MemoryX Agent Rules

MemoryX v3.0.0 - production-ready cognitive memory system.

## Absolute prohibitions

Agents must not:

- move, delete, recreate, or overwrite these tags:
  - v2.0.0
  - v2.0.0-rc.1
  - v2.0.0-rc.2
  - v3.0.0
- edit GitHub release assets
- edit runtime data:
  - .env
  - runtime DB
  - logs
  - traces
  - vector stores
  - lancedb runtime directories
- disable SQLite foreign keys
- use INSERT OR IGNORE to hide parent-row or FK errors
- make schema or migration changes without explicit batch approval
- use pytest skip/xfail to clear release failures
- run git add .
- tag from a dirty worktree
- publish from a dirty worktree
- mix docs/hygiene changes with core logic fixes
- treat Hermes update failures as MemoryX failures without attribution

## Phase 7 cognitive modules

The following modules were added in v3.0.0 and must NOT be modified without explicit approval:
- memoryx/cognitive/ebbinghaus.py (Ebbinghaus forgetting curve)
- memoryx/cognitive/working_memory.py (Baddeley model)
- memoryx/cognitive/dual_process.py (System 1 / System 2)
- memoryx/cognitive/predictive_coding.py (Active inference)
- memoryx/cognitive/cognitive_load.py (Cognitive load optimization)
- memoryx/cognitive/procedural_memory.py (Procedural memory)
- memoryx/consolidation/replay.py (Memory replay consolidation)