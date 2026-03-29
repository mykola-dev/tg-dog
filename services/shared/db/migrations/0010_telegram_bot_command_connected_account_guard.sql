ALTER TABLE telegram_bot_command_subscriptions
    ADD COLUMN IF NOT EXISTS allow_connected_account_only BOOLEAN NOT NULL DEFAULT TRUE;
