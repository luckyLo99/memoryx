# 2. Data Model: Evolution Nodes, Trajectories & the `memory_evolution` Table

This page documents the on-disk and in-memory data structures that power
the Evolutionary Trajectory feature. It is the source of truth for
developers extending or debugging the `memoryx.evolution` module.

> Code references in this document point at `memoryx/evolution/` and
> `memoryx/storage/sql/migrations/012_evolution_trajectory.sql`.

---

## 2.1 In-memory models (Pydantic-style dataclasses)

All three models live in `memoryx/evolution/models.py`.

### 2.1.1 `EvolutionKind` (enum)

Classifies what kind of evolution a node represents. The set is
deliberately small so that downstream code (detector, integration
layer, UI) can branch on it without ambiguity.

```python
class EvolutionKind(str, Enum):
    PREFERENCE = "PREFERENCE"  # "favorite X is Y", "I prefer Y"
    OPINION   = "OPINION"     # "I think Z is …"
    FACT      = "FACT"        # "I live in …", "I work as …"
```

### 2.1.2 `EvolutionNode` (dataclass)

A single value held by an entity in a slot, valid for a time window.
This is the atomic unit of the trajectory.

```python
@dataclass
class EvolutionNode:
    id: str                       # "evo_<12 hex>"
    entity_id: str                # typically the user id
    slot: str                     # canonical key, e.g. "singer"
    value: str                    # the value text, e.g. "张杰"
    kind: EvolutionKind           # PREFERENCE / OPINION / FACT
    valid_from: str               # ISO 8601 UTC
    valid_to: Optional[str]       # ISO 8601 UTC, None while active
    confidence: float = 1.0       # 0.0–1.0, comes from the detector
    source_memory_id: Optional[str]
    context: str = ""             # the source sentence (truncated to 500)
    created_at: str               # ISO 8601 UTC
    active_state: str = "active"  # active | superseded | archived
    decay_score: float = 0.0      # 1 - retention (Ebbinghaus)

    def is_active(self, as_of: Optional[str] = None) -> bool: ...
    def to_row(self) -> dict: ...                 # SQL serialization
    @classmethod
    def from_row(cls, row: dict) -> "EvolutionNode": ...
```

Field-by-field notes:

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Generated as `evo_<12 hex>`. |
| `entity_id` | yes | Scopes the trajectory to a user / agent. |
| `slot` | yes | Canonical key (see `PreferenceSignalDetector._canonicalize_slot`). |
| `value` | yes | The string value. Whitespace is normalized. |
| `kind` | yes | One of `PREFERENCE` / `OPINION` / `FACT`. |
| `valid_from` | yes | UTC ISO 8601. Set on insert. |
| `valid_to` | no | `null` while active. Set to the next node's `valid_from` on supersession. |
| `confidence` | yes | Defaults to `1.0`. Detector emits `0.85` for plain preference matches and `0.9` for explicit shift patterns. |
| `source_memory_id` | no | The original memory the signal was extracted from. |
| `context` | yes | The sentence that produced the signal, truncated to 500 chars. |
| `created_at` | yes | Row creation time, UTC ISO 8601. |
| `active_state` | yes | `active` (only one per `(entity, slot)`), `superseded` (older nodes), `archived` (soft-archived by the forgetting task). |
| `decay_score` | yes | `1 - retention`, recomputed by `apply_ebbinghaus_decay`. |

`is_active(as_of)` returns `True` only when `active_state == "active"`
and (if a timestamp is supplied) `as_of <= valid_to`. It is used by
queries that need to resolve the current value at a specific point in
time.

### 2.1.3 `EvolutionTrajectory` (dataclass)

An ordered view of every node for one `(entity_id, slot)` pair. It is
constructed on demand from the repository; it is **not** persisted as a
table row.

```python
@dataclass
class EvolutionTrajectory:
    entity_id: str
    slot: str
    nodes: list[EvolutionNode] = field(default_factory=list)

    @property
    def latest(self) -> Optional[EvolutionNode]: ...
    def to_dict(self) -> dict: ...
```

`latest` returns the active node with the highest `valid_from`, or
`None` if there is no active node. `to_dict` produces the
JSON-serializable shape used by the REST route and the Brain Bundle
export:

```json
{
  "entity_id": "u1",
  "slot": "singer",
  "latest": "房东的猫",
  "history": [
    { "id": "evo_aaa", "value": "张杰",
      "valid_from": "2025-09-01T12:00:00+00:00",
      "valid_to":   "2026-03-04T08:30:00+00:00",
      "context": "我最喜欢的歌星是张杰",
      "active_state": "superseded",
      "decay_score": 0.42 },
    { "id": "evo_bbb", "value": "房东的猫",
      "valid_from": "2026-03-04T08:30:00+00:00",
      "valid_to":   null,
      "context": "我最喜欢的歌星是房东的猫",
      "active_state": "active",
      "decay_score": 0.0 }
  ]
}
```

### 2.1.4 `PreferenceSignal` (dataclass)

The output of `PreferenceSignalDetector`. It is *not* a row; it is a
transient object the manager consumes and either drops (no change) or
turns into an `EvolutionNode`.

```python
@dataclass
class PreferenceSignal:
    entity_id: str
    slot: str
    value: str
    kind: EvolutionKind
    context: str = ""
    source_memory_id: Optional[str] = None
    confidence: float = 0.8
```

### 2.1.5 `EvolutionDecision` (enum)

The verdict of `EvolutionManager.decide(signal)`:

```python
class EvolutionDecision(str, Enum):
    ADD      = "ADD"      # brand-new (entity, slot) → first node
    EVOLVE   = "EVOLVE"   # existing slot, value differs from latest
    CONFLICT = "CONFLICT" # real contradiction, fall through to resolver
```

`EVOLVE` and `ADD` both result in a row being written. The difference
is only for logging and telemetry.

## 2.2 SQL schema: `memory_evolution`

The trajectory lives in its own table, in the same SQLite file as the
main memory store. The migration is
`memoryx/storage/sql/migrations/012_evolution_trajectory.sql`:

```sql
CREATE TABLE IF NOT EXISTS memory_evolution (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    slot TEXT NOT NULL,
    value TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'PREFERENCE',
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    source_memory_id TEXT,
    context TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    active_state TEXT NOT NULL DEFAULT 'active',
    decay_score REAL NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_evo_entity_slot
    ON memory_evolution(entity_id, slot, valid_from);

CREATE INDEX IF NOT EXISTS idx_evo_active_valid
    ON memory_evolution(active_state, valid_to);

CREATE INDEX IF NOT EXISTS idx_evo_source
    ON memory_evolution(source_memory_id);
```

Index rationale:

- `idx_evo_entity_slot` — the dominant query is "give me all nodes for
  `(entity_id, slot)` ordered by `valid_from`". This index covers it.
- `idx_evo_active_valid` — used by `get_active()` and
  `list_by_entity_slot(include_inactive=False)`, which filter on
  `active_state` and sometimes on `valid_to`.
- `idx_evo_source` — used by the "show me the trajectory nodes that
  came from this memory" back-link query.

The migration is idempotent: it uses `CREATE TABLE IF NOT EXISTS` and
`CREATE INDEX IF NOT EXISTS`, and is safe to re-run on every startup.

## 2.3 Supersession: how a new value "replaces" an old one

Supersession is the mechanism that lets two rows represent one evolving
fact without ever losing data. The `upsert_node` method on
`EvolutionRepository` performs the entire transition in a single
SQLite transaction:

1. Find all currently-`active` rows for the same `(entity_id, slot)`.
2. For each, set `valid_to = new_node.valid_from` and flip
   `active_state` from `active` to `superseded`. The row is **not**
   deleted; the original `value`, `context`, and `source_memory_id`
   stay intact.
3. Insert the new row with `valid_to = NULL` and
   `active_state = 'active'`.

The invariant the system maintains at all times is:

> For every `(entity_id, slot)` pair there is **at most one** row with
> `active_state = 'active'`, and its `valid_to` is `NULL`.

This is what makes `latest` cheap to compute and what lets
`get_trajectory` produce a clean, gap-free history.

Visually, after two `observe` calls (T1: 张杰, T2: 房东的猫):

```
memory_evolution
┌──────────┬────────┬──────────┬─────────────────────┬─────────────────────┬────────────┐
│ id       │ slot   │ value    │ valid_from          │ valid_to            │ active_state│
├──────────┼────────┼──────────┼─────────────────────┼─────────────────────┼────────────┤
│ evo_aaa  │ singer │ 张杰     │ 2025-09-01T12:00Z   │ 2026-03-04T08:30Z   │ superseded │
│ evo_bbb  │ singer │ 房东的猫 │ 2026-03-04T08:30Z   │ NULL                │ active     │
└──────────┴────────┴──────────┴─────────────────────┴─────────────────────┴────────────┘
```

A third observe (T3: 周深) produces:

```
memory_evolution
┌──────────┬────────┬──────────┬─────────────────────┬─────────────────────┬────────────┐
│ id       │ slot   │ value    │ valid_from          │ valid_to            │ active_state│
├──────────┼────────┼──────────┼─────────────────────┼─────────────────────┼────────────┤
│ evo_aaa  │ singer │ 张杰     │ 2025-09-01T12:00Z   │ 2026-03-04T08:30Z   │ superseded │
│ evo_bbb  │ singer │ 房东的猫 │ 2026-03-04T08:30Z   │ 2026-09-12T17:00Z   │ superseded │
│ evo_ccc  │ singer │ 周深     │ 2026-09-12T17:00Z   │ NULL                │ active     │
└──────────┴────────┴──────────┴─────────────────────┴─────────────────────┴────────────┘
```

`get_active("u1", "singer")` returns the row whose `active_state =
'active'`. `get_trajectory("u1", "singer")` returns all three rows in
`valid_from` order. Nothing is ever lost.

## 2.4 Ebbinghaus decay without deletion

A trajectory node follows the same forgetting curve as ordinary
memories, with one critical difference: **the row is never deleted.**
`apply_ebbinghaus_decay` only updates `decay_score`, which downstream
layers use to *down-weight* an old node, never to remove it.

The math is the standard Ebbinghaus retention curve:

```
retention(t) = e ^ (-t / S)
decay_score  = 1 - retention
```

where `t` is the number of hours since `valid_from` and `S` is the
half-life. The default `S` is `24 * 30` hours (~30 days), which mirrors
the rest of MemoryX.

Practical consequences:

| Time after `valid_from` | `retention` (S = 30d) | `decay_score` | Visible via `get_trajectory`? |
|---|---|---|---|
| 0 hours | 1.000 | 0.000 | yes |
| 24 hours | 0.926 | 0.074 | yes |
| 30 days | 0.368 | 0.632 | yes |
| 90 days | 0.050 | 0.950 | yes |
| 6 months | 0.002 | 0.998 | yes |
| 2 years | ≈ 0 | ≈ 1.0 | yes |

The `get_active()` query used by the behavior layer filters on
`active_state = 'active'`, not on `decay_score`, so even a node that
has fully decayed still counts as the *current* value of its slot
until it is superseded by a newer one. Old nodes only leave the
"current" position when a new signal arrives, never because of time
alone.

The forgetting task (Phase 5 of the spec) can *soft-archive* a node
(flip `active_state` to `archived`) but the row remains in the table
and remains visible to `get_trajectory(include_inactive=True)`. The
spec calls this "保留但降权" — *keep, but down-weight*.

This combination — soft supersession by the manager, soft archival by
the forgetting task, and pure score-based decay — is what makes the
trajectory both a faithful history of the user and a cheap, indexed
source of "what does this user currently prefer?".
