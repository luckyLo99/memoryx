# 1. Concept: Evolutionary Trajectory

> People don't get things *wrong* — they grow. MemoryX models this growth as
> an **Evolutionary Trajectory** (成长轨迹): an ordered, time-anchored record of
> how a preference, opinion, or fact has changed for an entity, rather than
> a contradiction between two memories.

---

## 1.1 Why "evolution" instead of "conflict"?

Traditional memory systems treat any semantic disagreement between an old
memory and a new one as a **conflict**. That is the right call for hard
facts (e.g. "Paris is the capital of Germany" vs. "Paris is the capital of
France"). It is the **wrong** call for the kind of information that defines
a person: their tastes, their opinions, their favorite anything.

When a user said "my favorite singer is 张杰" last year and "my favorite
singer is 房东的猫" this month, nothing is broken. They are not lying to
themselves, and they are not in conflict. They have simply **changed**, the
way people do.

MemoryX therefore introduces a parallel path in the pipeline:

| Kind of change | How MemoryX treats it |
|---|---|
| Hard fact contradiction ("Paris is in Germany" vs "…France") | **Conflict** — surfaced to the resolver, user is asked to disambiguate |
| Preference / opinion / soft-fact shift | **Evolution** — appended to the entity's trajectory, old value kept, new value becomes "current" |

The two paths are not in tension. They answer different questions:

- Conflict detection answers: *"Is one of these statements factually wrong?"*
- Evolution answers: *"How has this person's view changed over time?"*

## 1.2 The canonical case: 张杰 → 房东的猫

This is the example used throughout the rest of the docs and the test
suite. It is deliberately simple, in two languages (Chinese and English),
and not fact-checkable — exactly the kind of change that should *not*
trigger a conflict alarm.

**Timeline**

| Time | Source text | Detected signal |
|---|---|---|
| T1 | `我最喜欢的歌星是张杰` | preference: singer = 张杰 |
| T2 (T2 > T1) | `我最喜欢的歌星是房东的猫` | preference: singer = 房东的猫 |

**What MemoryX does**

1. On T1, the extractor detects a `PREFERENCE` signal and writes a node
   to the trajectory:
   `{"value": "张杰", "valid_from": T1, "active_state": "active"}`
2. On T2, a second `PREFERENCE` signal is detected for the *same slot*
   (`singer`) but with a *different value* (`房东的猫`).
3. The EvolutionManager appends a new node and marks the previous one
   `superseded` — the row is **not** deleted.
4. The conflict resolver is **not** invoked. No alarm is raised.
5. Behavior layer reads `latest` → `房东的猫`.
6. The user (or an audit query) can still read the full timeline and see
   that the user once preferred 张杰 and now prefers 房东的猫.

This is the difference between a memory system that knows a *fact* and one
that knows a *person*.

## 1.3 How it differs from conflict detection

The two mechanisms are intentionally complementary. MemoryX routes a new
incoming memory through both:

```
incoming memory
       │
       ▼
┌──────────────────┐    yes    ┌────────────────────────┐
│ preference /     │──────────▶│  EvolutionManager      │
│ opinion / fact   │           │  append to trajectory  │
│ shift detected?  │           │  (skip conflict alarm) │
└────────┬─────────┘           └────────────────────────┘
         │ no
         ▼
┌──────────────────┐    yes    ┌────────────────────────┐
│ hard-fact contra-│──────────▶│  ConflictResolver      │
│ diction detected?│           │  raise conflict alarm  │
└────────┬─────────┘           └────────────────────────┘
         │ no
         ▼
   add as new memory
```

The two checks do not overlap. A preference change never reaches the
conflict resolver, and a hard-fact contradiction never reaches the
EvolutionManager. If both fire (which is rare and indicates a hard rule
violation), conflict wins by design.

| Dimension | Conflict detection | Evolutionary trajectory |
|---|---|---|
| Trigger | "These two statements cannot both be true" | "The user has expressed a different view of the same slot" |
| Resolution | Ask the user / pick a winner | Append a new node, keep the old one |
| Retention | Loser often dropped or quarantined | Both kept, ordered, time-stamped |
| Surface | Alarm to the user / agent | Quiet; available via `get_trajectory` |
| Decay | Same as ordinary memory | Ebbinghaus decay on `decay_score`, but row is never deleted |
| Scope | Per memory record | Per `(entity_id, slot)` pair |

## 1.4 Trajectory structure

A **trajectory** is the sequence of values an entity has held in one named
slot over time. The slot is a canonical key such as `singer`, `color`,
`food`, `book`, `movie`, `sport`, `pet`. Each element of the trajectory is
an `EvolutionNode` — a value plus the time window during which it was
"current".

```
EvolutionTrajectory
├── entity_id : "u1"
├── slot      : "singer"
└── nodes     : [ EvolutionNode, EvolutionNode, … ]

EvolutionNode
├── id              : "evo_a1b2c3…"
├── entity_id       : "u1"
├── slot            : "singer"
├── value           : "张杰"
├── kind            : PREFERENCE | OPINION | FACT
├── valid_from      : "2025-09-01T12:00:00+00:00"
├── valid_to        : "2026-03-04T08:30:00+00:00"   # null while active
├── confidence      : 0.85
├── source_memory_id: "mem_…"
├── context         : "我最喜欢的歌星是张杰"
├── created_at      : "…"
├── active_state    : "active" | "superseded" | "archived"
└── decay_score     : 0.0  # 0 = fresh, increases with time (1 - retention)
```

Key properties:

- **Append-only at the trajectory level.** You never overwrite a node. A
  new value always creates a *new* node and demotes the previous active
  one to `superseded`.
- **Time-anchored.** Every node carries `valid_from` and (after
  supersession) `valid_to`, so the trajectory can be replayed at any
  past timestamp.
- **Per `(entity_id, slot)`.** Two different slots evolve independently:
  a user can change their favorite singer without changing their
  favorite color.
- **Decoupled from decay.** A node can be deeply decayed (low
  activation) but still fully present in the trajectory. The user
  never loses their own history.

The next pages describe the concrete data model (`02_data_model.md`) and
the manager API (`03_api.md`).
