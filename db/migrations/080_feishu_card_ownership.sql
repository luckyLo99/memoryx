-- P14.4.3 Feishu Card Ownership: DB schema for card message tracking
-- This table persists outbound card message IDs so we can patch the same card

CREATE TABLE IF NOT EXISTS feishu_card_messages (
    job_id TEXT PRIMARY KEY,
    inbound_message_id TEXT,
    outbound_card_message_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    sender_identity TEXT NOT NULL DEFAULT 'app_bot',
    card_schema TEXT NOT NULL DEFAULT '2.0',
    update_multi INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feishu_card_messages_outbound
ON feishu_card_messages(outbound_card_message_id);

CREATE INDEX IF NOT EXISTS idx_feishu_card_messages_chat
ON feishu_card_messages(chat_id, created_at);

-- Ensure feishu_jobs.card_message_id column exists (it should already)
-- If not, add it:
-- ALTER TABLE feishu_jobs ADD COLUMN card_message_id TEXT;
