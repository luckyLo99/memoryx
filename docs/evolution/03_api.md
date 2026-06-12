# 3. API: `EvolutionManager` & `EvolutionIntegration`

This page is the developer-facing reference for working with the
Evolutionary Trajectory module. It covers the four public methods of
`EvolutionManager` (`observe`, `get_trajectory`, `decide`,
`apply_ebbinghaus_decay`) and the `EvolutionIntegration` helper used
to wire the manager into the existing memory pipeline.

All symbols are exported from the top-level package:

```python
from memoryx.evolution import (
    EvolutionManager,
    EvolutionIntegration,
    EvolutionNode,
    EvolutionTrajectory,
    EvolutionDecision,
    EvolutionKind,
    PreferenceSignal,
    IntegrationDecision,
)
```

---

## 3.1 `EvolutionManager`

`EvolutionManager` is the orchestrator. It owns a
`PreferenceSignalDetector` (heuristic) and an
`EvolutionRepository` (SQLite-backed CRUD). It is the only place that
decides whether a new observation is an `ADD`, an `EVOLVE`, or a
`CONFLICT`.

```python
from pathlib import Path
from memoryx.evolution import EvolutionManager, EvolutionRepository

repo   = EvolutionRepository(Path("./memory.db"))
manager = EvolutionManager(repository=repo)
```

### 3.1.1 `observe(content, entity_id="user", memory_id=None) -> list[EvolutionNode]`

Detect preference / opinion / fact signals in a free-form string and
append them to the appropriate trajectories. This is the **only** call
the application layer normally needs to make.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `content` | `str` | — | The text to analyze. Typically the latest user message or a memory candidate. |
| `entity_id` | `str` | `"user"` | The trajectory owner. For a multi-tenant setup use the actual user id. |
| `memory_id` | `Optional[str]` | `None` | If the text came from a stored memory, pass its id. It is recorded as `source_memory_id` for back-linking. |

**Returns** — the list of `EvolutionNode` rows that were actually
written. If a signal is a duplicate of the current `latest` value, no
row is written and that signal is silently dropped from the result.

**Example — the canonical 张杰 → 房东的猫 case**

```python
# T1
nodes_t1 = manager.observe("我最喜欢的歌星是张杰", entity_id="u1")
print(nodes_t1[0].value)            # "张杰"
print(nodes_t1[0].active_state)      # "active"
print(nodes_t1[0].valid_to)          # None

# T2 (later)
nodes_t2 = manager.observe("我最喜欢的歌星是房东的猫", entity_id="u1")
print(nodes_t2[0].value)            # "房东的猫"
print(nodes_t2[0].active_state)      # "active"
print(nodes_t2[0].valid_to)          # None
```

After both calls, the trajectory for `(u1, "singer")` has two rows:
the 张杰 row is now `superseded` with `valid_to == nodes_t2[0].valid_from`,
and the 房东的猫 row is `active`.

Internally `observe` calls `PreferenceSignalDetector.detect(...)`
which recognizes, among others:

- `我最喜欢的 X 是 Y` / `我最爱 X 是 Y` (Chinese preference)
- `my favorite X is Y` (English preference)
- `我最喜欢的 X 是 Y，现在最喜欢的是 Z` (explicit shift, higher confidence)

The detector canonicalizes slot names so that 歌星 / 歌手 / 明星 /
偶像 all map to `"singer"`, ensuring both observations land in the
same trajectory.

### 3.1.2 `get_trajectory(entity_id, slot) -> EvolutionTrajectory`

Return every node for one `(entity_id, slot)` pair, **including
superseded and archived ones**, ordered by `valid_from` ascending.

| Parameter | Type | Notes |
|---|---|---|
| `entity_id` | `str` | The trajectory owner. |
| `slot` | `str` | Canonical slot key, e.g. `"singer"`, `"color"`, `"food"`. |

**Returns** — an `EvolutionTrajectory` with:

- `nodes` — every row in `valid_from` order.
- `latest` (property) — the single active node with the highest
  `valid_from`, or `None` if there is no active node.

**Example**

```python
traj = manager.get_trajectory("u1", "singer")
print("current favorite singer:", traj.latest.value)  # "房东的猫"

for n in traj.nodes:
    print(f"  {n.valid_from}  {n.value}  ({n.active_state})")
# 2025-09-01T12:00:00+00:00  张杰     (superseded)
# 2026-03-04T08:30:00+00:00  房东的猫 (active)
```

`EvolutionTrajectory.to_dict()` is the JSON-serializable form used by
the REST route and the Brain Bundle export.

### 3.1.3 `decide(signal) -> EvolutionDecision`

Pure routing helper. Tells the caller what *would* happen to a
`PreferenceSignal` if it were passed to `upsert_node`. It does **not**
write to the database; it only inspects the current state.

| Returned decision | When |
|---|---|
| `ADD` | No active row exists for `(entity_id, slot)`, **or** the signal's value equals the current `latest.value` (no-op duplicate). |
| `EVOLVE` | An active row exists, and the signal's value differs from it. |
| `CONFLICT` | The caller has separately determined that the new value contradicts a hard fact. (The manager itself does not raise this; see `EvolutionIntegration.route`.) |

Typical use: in the conflict-detection wrapper, call `decide` first;
if it returns `ADD` or `EVOLVE`, skip the conflict alarm and route to
the evolution manager instead.

```python
from memoryx.evolution import PreferenceSignal, EvolutionKind

sig = PreferenceSignal(
    entity_id="u1",
    slot="singer",
    value="房东的猫",
    kind=EvolutionKind.PREFERENCE,
)
print(manager.decide(sig).value)   # "EVOLVE"
```

### 3.1.4 `apply_ebbinghaus_decay(half_life_hours=24*30) -> int`

Recompute `decay_score` for every active node currently in the store
using the Ebbinghaus retention formula:

```
retention(t) = e ^ (-t / S)     # S = half_life_hours
decay_score  = 1 - retention
```

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `half_life_hours` | `float` | `24 * 30` (~30 days) | The forgetting-curve "S" parameter. Larger → slower decay. |

**Returns** — the number of nodes whose `decay_score` was updated.
Call this from a scheduled job (cron, the system maintenance timer,
etc.) — the manager does not run it on a timer by itself.

```python
updated = manager.apply_ebbinghaus_decay()      # uses default S = 30 days
print(f"refreshed decay on {updated} nodes")
```

Important: `apply_ebbinghaus_decay` only writes a new
`decay_score`. It never changes `active_state` and never deletes a
row. A fully decayed node is still the `latest` value of its slot
until a new observation supersedes it.

## 3.2 End-to-end usage example

A full happy path, from the first preference signal to a trajectory
read-out:

```python
from pathlib import Path
from memoryx.evolution import EvolutionManager, EvolutionRepository

# 1) Construct the manager (idempotent: creates the table if needed)
manager = EvolutionManager(
    repository=EvolutionRepository(Path("./memory.db"))
)

# 2) T1 — user says their favorite singer is 张杰
manager.observe("我最喜欢的歌星是张杰", entity_id="u1")

# 3) T2 — six months later, the user changes their mind
manager.observe("我最喜欢的歌星是房东的猫", entity_id="u1")

# 4) Read the full trajectory
traj = manager.get_trajectory("u1", "singer")
print(traj.to_dict())
# {
#   "entity_id": "u1",
#   "slot": "singer",
#   "latest": "房东的猫",
#   "history": [
#     {"value": "张杰",     "active_state": "superseded", ...},
#     {"value": "房东的猫", "active_state": "active",     ...}
#   ]
# }

# 5) Periodically refresh decay scores
manager.apply_ebbinghaus_decay()
```

If you want the **current** value without iterating the trajectory,
use `get_latest`:

```python
node = manager.get_latest("u1", "singer")
print(node.value)        # "房东的猫"
print(node.confidence)   # 0.85 (or 0.9 if it came from an explicit shift)
```

## 3.3 `EvolutionIntegration` — pipeline glue

`EvolutionIntegration` is a thin wrapper that lets the rest of the
memory pipeline interact with `EvolutionManager` without importing
it directly. It is the seam that keeps the manager optional and
the pipeline backward-compatible.

```python
from memoryx.evolution import EvolutionIntegration, EvolutionManager

integration = EvolutionIntegration(manager=manager)
# or, if evolution is disabled:
integration = EvolutionIntegration(manager=None)   # becomes a no-op
```

### 3.3.1 `observe_content(content, entity_id="user", memory_id=None)`

Convenience pass-through to `EvolutionManager.observe`. Returns an
empty list if no manager is wired. Call this from the extractor or
the post-write hook.

```python
nodes = integration.observe_content(
    content="我最喜欢的歌星是房东的猫",
    entity_id="u1",
    memory_id="mem_42",
)
```

### 3.3.2 `route(signal) -> IntegrationDecision`

The recommended way to integrate with the existing
`ConflictResolver`. The resolver wrapper should:

1. Build a candidate `PreferenceSignal` from the new memory.
2. Call `integration.route(signal)`.
3. If `decision.is_evolution` is `True`, **skip** the conflict alarm
   and let the new node be appended by the manager.
4. If `decision.decision == EvolutionDecision.CONFLICT`, fall through
   to the normal conflict flow.

```python
from dataclasses import dataclass

@dataclass
class IntegrationDecision:
    is_evolution: bool
    node: Optional[EvolutionNode] = None
    decision: EvolutionDecision = EvolutionDecision.ADD
    reason: str = ""
```

| Field | Meaning |
|---|---|
| `is_evolution` | `True` if the signal was treated as an evolution event. Callers can skip the conflict alarm. |
| `node` | The `EvolutionNode` that was written (or `None`). |
| `decision` | The underlying `ADD` / `EVOLVE` / `CONFLICT` verdict. |
| `reason` | Short human-readable tag (`"new_slot"`, `"appended"`, `"conflict"`, `"no_manager"`) for logs and telemetry. |

### 3.3.3 `is_preference_change(content) -> bool`

Cheap pre-check used by extractors and routers to decide whether it is
worth even building a `PreferenceSignal`. Returns `True` if the
text contains at least one preference-like pattern.

```python
if integration.is_preference_change(user_message):
    # …build signal, call route, etc.
    ...
```

## 3.4 Putting it together — wiring the extractor

The canonical integration point is the extractor (or any post-write
hook). A minimal example:

```python
# In the extraction / write path:

# 1. The new memory has just been identified.
new_memory_text = "我最喜欢的歌星是房东的猫"
new_memory_id   = "mem_42"

# 2. Quick filter.
if integration.is_preference_change(new_memory_text):
    # 3. Observe directly. observe() will detect the signal,
    #    de-dup against latest, and append if different.
    nodes = integration.observe_content(
        content=new_memory_text,
        entity_id="u1",
        memory_id=new_memory_id,
    )
    # 4. Skip the conflict alarm — this is an evolution event,
    #    not a hard-fact contradiction.
```

The conflict resolver, if it runs at all, will see no active conflict
and pass the memory through.

## 3.5 Backward compatibility

`EvolutionIntegration` and `EvolutionManager` are designed to be
opt-in. If no manager is wired (or the `memory_evolution` table does
not exist), every call returns a safe default:

- `observe_content` returns `[]` — no nodes written, no exception.
- `route` returns `IntegrationDecision(is_evolution=False, reason="no_manager")`.
- `is_preference_change` returns `False`.

This means rolling out the feature to an existing MemoryX install is
a non-event: the table is created on first access by
`EvolutionRepository.__init__`, and no existing call sites need to
change unless they want to participate.
