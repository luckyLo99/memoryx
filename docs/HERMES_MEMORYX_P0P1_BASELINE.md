# Hermes MemoryX P0/P1 Stability Baseline

Date: 2026-06-06  
Branch: `p0-p1-hermes-memoryx-stability`  
Commit: `db14112`  
Tag: `hermes-memoryx-p0p1-stable-20260606`  
Author: MemoryX + Hermes P0/P1 stabilization

---

## Final DB State

| Metric | Value |
|--------|-------|
| active FACT | 14 |
| active PERSONA | 5 |
| archived FACT | 75 |
| active_over_500 | 0 |
| sync_turn garbage | 0 |
| total injection chars | 4,444 |
| SOUL.md | 6,171 bytes |

---

## Provider Changes Applied

| File | Change |
|------|--------|
| `__init__.py` | `AsyncLoopRunner` — single background event loop via `run_coroutine_threadsafe`, reused across provider lifetime. `MEMORYX_AUTO_SYNC_TURNS=0` default. sync_turn via single Queue + worker. metadata/tags enriched with session_id, confidence, importance, memory_type. CJK LIKE fallback when FTS5 returns empty. |
| `storage/sqlite_async.py` | `_inside_transaction` global boolean → `ContextVar` for per-task isolation. |
| `extraction/client.py` | Fixed `api_key` hardcoded to `"your_api_key_here"` — now uses passed parameter. |
| `retrieval/engine.py` | Fixed `_entity_overlap` list-unhashable bug. `MIN_FINAL_SCORE` configurable via env var. |
| `storage/repository.py` | Unified `EPISODE` → `EPISODIC`. DB migration applied. |

---

## Data Cleanup Summary

| Phase | active FACT | active PERSONA | archived |
|-------|:-----------:|:--------------:|:--------:|
| Before cleanup | 76 | 5 | 6 |
| After cleanup | 14 | 5 | 75 |
| **Net change** | **-62** | **0** | **+69** |

65 entries archived (test noise, sync_turn garbage, validation artifacts).  
All remaining entries trimmed to ≤500 chars.

---

## Injection Path Verification

Source code review (`agent/system_prompt.py` lines 300–326) confirmed **exclusive** memory injection at the system prompt layer:

```
if MemoryXProvider.system_prompt_block() returns non-empty:
    inject MemoryX block → _ext_mem_used = True
    skip built-in ~/.hermes/memories/MEMORY.md / USER.md
else:
    _ext_mem_used = False
    fall back to built-in file memory
```

### Current protection layers

| Risk | Status |
|------|--------|
| MemoryX returns empty → fallback to files | MemoryX has 19 active entries, returns 4,444 chars — non-empty |
| Legacy MEMORY.md / USER.md pollute fallback | Backed up and zeroed (0 bytes each) |
| `on_memory_write` writes back to files | `MEMORYX_AUTHORITATIVE=1` → early return, no file write |
| sync_turn stores full dialogue | `MEMORYX_AUTO_SYNC_TURNS=0`, DB check = 0 |
| Over-length entries inflate injection | `active_over_500 = 0` |

**Conclusion:** MemoryX is the sole active memory injection source. Built-in file memory exists as a zero-byte fallback only.

---

## Frozen Items

Do NOT change during the 24–72 hour observation period:

- Stage 2 RRF (retrieval fusion)
- Embedding backend
- Context injection logic
- Provider lifecycle (AsyncLoopRunner, repo reuse)
- DB schema
- Model / fallback / delegation configuration
- `/new` behavior

---

## Observation Pass Criteria

| Criterion | Target |
|-----------|--------|
| `active_over_500` | Remains 0 |
| `sync_turn garbage` | Remains 0 |
| English `memoryx_search` | Works without error |
| Chinese `memoryx_search` | LIKE fallback works without error |
| `memoryx_store` | Writes compact entries (≤500 chars) |
| Provider lifecycle | No errors after `/new` |
| `MEMORY.md` / `USER.md` | Remain 0 bytes (no re-population) |

---

## Observation Check Command

```bash
DB="${MEMORYX_HOME:-$HOME/.hermes/memoryx}/memoryx.db"

echo "=== counts ==="
sqlite3 -header -column "$DB" \
  "SELECT active_state, memory_type, COUNT(*) FROM memories
   GROUP BY active_state, memory_type ORDER BY active_state, memory_type;"

echo "=== active_over_500 ==="
sqlite3 "$DB" \
  "SELECT COUNT(*) FROM memories
   WHERE active_state='active' AND length(content) > 500;"

echo "=== sync_garbage ==="
sqlite3 "$DB" \
  "SELECT COUNT(*) FROM memories WHERE active_state='active'
   AND (content LIKE '%User:%Assistant:%'
        OR lower(metadata_json) LIKE '%sync_turn%');"

echo "=== legacy files ==="
wc -c ~/.hermes/memories/MEMORY.md ~/.hermes/memories/USER.md

echo "=== Chinese search ==="
sqlite3 "$DB" \
  "SELECT COUNT(*) FROM memories
   WHERE active_state='active' AND content LIKE '%中文%';"
```

---

## Stage 2 Trigger Condition

Enter Stage 2 (RRF design only, no code patches) only after:

1. At least one full real-use cycle completed
2. All observation pass criteria still met
3. Provider lifecycle confirmed stable with no errors

Stage 2 first step: produce RRF design document + 20–30 query Chinese/English benchmark. Do not apply patches.
