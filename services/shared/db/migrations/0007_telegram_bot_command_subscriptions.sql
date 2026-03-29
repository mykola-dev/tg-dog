CREATE TABLE IF NOT EXISTS telegram_bot_command_subscriptions (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    webhook_mode TEXT NOT NULL DEFAULT 'production',
    command TEXT NOT NULL,
    allowed_chat_ids TEXT NOT NULL DEFAULT '',
    webhook_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workflow_id, node_id, webhook_mode)
);

CREATE INDEX IF NOT EXISTS ix_telegram_bot_command_subscriptions_command
    ON telegram_bot_command_subscriptions (command);
