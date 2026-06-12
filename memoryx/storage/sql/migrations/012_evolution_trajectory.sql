-- Migration 012: Evolutionary Trajectory
-- Tracks how user preferences, opinions, and facts change over time
-- without flagging them as conflicts (e.g. favorite singer: 张杰 → 房东的猫).

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
