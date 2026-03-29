ALTER TABLE telegram_bot_command_subscriptions
    ADD COLUMN IF NOT EXISTS allowed_user_ids TEXT NOT NULL DEFAULT '';

ALTER TABLE telegram_bot_command_subscriptions
    ADD COLUMN IF NOT EXISTS require_private_chat BOOLEAN NOT NULL DEFAULT TRUE;
