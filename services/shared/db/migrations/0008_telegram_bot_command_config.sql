CREATE TABLE IF NOT EXISTS telegram_bot_command_config (
    id INTEGER PRIMARY KEY,
    webhook_base_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO telegram_bot_command_config (id, webhook_base_url)
VALUES (1, NULL)
ON CONFLICT (id) DO NOTHING;
