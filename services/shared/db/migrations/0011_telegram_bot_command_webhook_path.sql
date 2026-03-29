ALTER TABLE telegram_bot_command_subscriptions
    ADD COLUMN IF NOT EXISTS webhook_path TEXT NOT NULL DEFAULT '';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'telegram_bot_command_subscriptions'
          AND column_name = 'webhook_url'
    ) THEN
        UPDATE telegram_bot_command_subscriptions
        SET webhook_path = regexp_replace(COALESCE(webhook_url, ''), '^https?://[^/]+/webhook/', '')
        WHERE webhook_path = '';

        ALTER TABLE telegram_bot_command_subscriptions DROP COLUMN IF EXISTS webhook_url;
    END IF;
END $$;

ALTER TABLE telegram_bot_command_subscriptions
    DROP COLUMN IF EXISTS allowed_chat_ids;

ALTER TABLE telegram_bot_command_subscriptions
    DROP COLUMN IF EXISTS allowed_user_ids;
