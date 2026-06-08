# Adaptive Context Planner

Phase 15.6 adds adaptive context modes.

## Modes

| Mode | Max tokens | Use case |
|---|---:|---|
| tiny | 2048 | ultra-small calls |
| brief | 4096 | simple questions |
| standard | 8192 | default agent use |
| deep | 16384 | architecture, migration, debugging, phase work |
| debug | 32768 | explicit diagnostics only |

The planner selects a mode from the query unless the caller explicitly passes `mode`.

## Rule

Default prompt injection must remain budgeted. Larger modes are explicit and still capped.
