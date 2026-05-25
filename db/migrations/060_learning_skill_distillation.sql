-- P16: Learning Loop + Skill Distillation
-- Date: 2026-05-25
-- Depends: 050_trust_conflict_forgetting.sql (P15.1)

-- ── Learning Projects ──
CREATE TABLE IF NOT EXISTS learning_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    objective TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── Learning Sessions ──
CREATE TABLE IF NOT EXISTS learning_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    goal TEXT NOT NULL DEFAULT '',
    mastery_target TEXT NOT NULL DEFAULT '会用',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    duration_seconds INTEGER,
    summary TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_learning_sessions_project
ON learning_sessions(project_id, started_at);

CREATE INDEX IF NOT EXISTS idx_learning_sessions_session
ON learning_sessions(session_id);

-- ── Learning Artifacts ──
CREATE TABLE IF NOT EXISTS learning_artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    path TEXT,
    trust_score REAL NOT NULL DEFAULT 0.7,
    source_type TEXT NOT NULL DEFAULT 'learning_session',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_learning_artifacts_project
ON learning_artifacts(project_id, artifact_type, created_at);

-- ── Mastery Checks ──
CREATE TABLE IF NOT EXISTS mastery_checks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    level TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    weak_points_json TEXT NOT NULL DEFAULT '[]',
    next_tasks_json TEXT NOT NULL DEFAULT '[]',
    score REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mastery_checks_topic
ON mastery_checks(project_id, topic, created_at);

-- ── Skill Atoms ──
CREATE TABLE IF NOT EXISTS skill_atoms (
    id TEXT PRIMARY KEY,
    source_session_id TEXT,
    source_job_id TEXT,
    source_trace_id TEXT,
    atom_type TEXT NOT NULL,
    intent TEXT NOT NULL,
    summary TEXT NOT NULL,
    raw_excerpt TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    trust_score REAL NOT NULL DEFAULT 0.5,
    ux_score REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skill_atoms_type
ON skill_atoms(atom_type, created_at);

-- ── Skill Candidates ──
CREATE TABLE IF NOT EXISTS skill_candidates (
    id TEXT PRIMARY KEY,
    skill_key TEXT NOT NULL,
    atom_id TEXT NOT NULL,
    contribution TEXT NOT NULL,
    weight_score REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skill_candidates_skill
ON skill_candidates(skill_key, status, created_at);

-- ── Skill Drafts ──
CREATE TABLE IF NOT EXISTS skill_drafts (
    id TEXT PRIMARY KEY,
    skill_key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    skill_markdown TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TEXT,
    installed_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_skill_drafts_status
ON skill_drafts(status, created_at);

-- ── Skill UX Scores ──
CREATE TABLE IF NOT EXISTS skill_ux_scores (
    id TEXT PRIMARY KEY,
    skill_key TEXT NOT NULL,
    draft_id TEXT,
    session_id TEXT,
    side TEXT NOT NULL DEFAULT 'draft',
    score REAL NOT NULL,
    reasons TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skill_ux_scores_skill
ON skill_ux_scores(skill_key, side, created_at);