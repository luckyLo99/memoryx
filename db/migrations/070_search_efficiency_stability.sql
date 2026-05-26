-- P18: Search Efficiency + Stability
-- Date: 2026-05-25
-- Depends: 060_learning_skill_distillation.sql

PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS session_search_index (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    ended_at TEXT,
    duration_seconds INTEGER,
    turn_count INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,

    summary TEXT NOT NULL DEFAULT '',
    keywords_json TEXT NOT NULL DEFAULT '[]',
    entities_json TEXT NOT NULL DEFAULT '[]',
    topics_json TEXT NOT NULL DEFAULT '[]',

    content_hash TEXT NOT NULL DEFAULT '',
    summary_model TEXT NOT NULL DEFAULT '',
    summary_updated_at TEXT,

    embedding_id TEXT,
    trust_score REAL NOT NULL DEFAULT 0.7,
    active_state TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS session_search_fts USING fts5(
    session_id UNINDEXED,
    title,
    summary,
    keywords,
    entities,
    topics,
    content='',
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS session_search_cache (
    id TEXT PRIMARY KEY,
    query_hash TEXT NOT NULL,
    session_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    answer TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0.0,
    model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(query_hash, session_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_session_search_index_time
ON session_search_index(started_at, ended_at);

CREATE INDEX IF NOT EXISTS idx_session_search_index_active
ON session_search_index(active_state, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_session_search_cache_lookup
ON session_search_cache(query_hash, session_id, content_hash, expires_at);