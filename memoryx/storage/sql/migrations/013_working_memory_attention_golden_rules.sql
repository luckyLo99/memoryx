-- Migration 013: Working Memory Persistence, Attention Focus, and Golden Rules
-- Adds tables for:
--   1. working_memory: persistent short-term memory (30-min TTL)
--   2. attention_frames: attention focus tracking with activation decay
--   3. golden_rules: user corrections with absolute priority

-- =============================================================================
-- Working Memory (持久化短期记忆)
-- =============================================================================

CREATE TABLE IF NOT EXISTS working_memory (
    session_id TEXT PRIMARY KEY,
    current_task TEXT NOT NULL DEFAULT '',
    reasoning_chain TEXT NOT NULL DEFAULT '[]',
    active_todos TEXT NOT NULL DEFAULT '[]',
    temporary_context TEXT NOT NULL DEFAULT '{}',
    debug_session TEXT NOT NULL DEFAULT '{}',
    workflow_state TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL DEFAULT (datetime('now', '+1800 seconds'))
);

CREATE INDEX IF NOT EXISTS idx_working_memory_expires
    ON working_memory(expires_at);

-- =============================================================================
-- Attention Frames (注意力焦点追踪)
-- =============================================================================

CREATE TABLE IF NOT EXISTS attention_frames (
    task_id TEXT PRIMARY KEY,
    task_description TEXT NOT NULL DEFAULT '',
    reasoning_chain TEXT NOT NULL DEFAULT '[]',
    active_todos TEXT NOT NULL DEFAULT '[]',
    activation REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_accessed_at TEXT NOT NULL DEFAULT (datetime('now')),
    parent_task_id TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_attention_frames_activation
    ON attention_frames(activation DESC);

CREATE INDEX IF NOT EXISTS idx_attention_frames_parent
    ON attention_frames(parent_task_id);

-- =============================================================================
-- Golden Rules (用户纠正的绝对规则)
-- =============================================================================

CREATE TABLE IF NOT EXISTS golden_rules (
    rule_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    content TEXT NOT NULL,
    original_content TEXT,
    correction_source TEXT NOT NULL DEFAULT 'user_explicit',
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    suppresses_patterns TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL DEFAULT 'global',
    session_id TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_golden_rules_memory
    ON golden_rules(memory_id);

CREATE INDEX IF NOT EXISTS idx_golden_rules_scope_session
    ON golden_rules(scope, session_id);

-- =============================================================================
-- Memories: add golden rule columns
-- =============================================================================

ALTER TABLE memories ADD COLUMN is_golden INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN golden_priority REAL DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_memories_golden
    ON memories(is_golden, golden_priority) WHERE is_golden = 1;
