ALTER TABLE telegram_bot_command_config
    ADD COLUMN IF NOT EXISTS webhook_mode TEXT NOT NULL DEFAULT 'webhook';

UPDATE telegram_bot_command_config
SET webhook_mode = CASE
    WHEN COALESCE(webhook_base_url, '') = '' THEN 'polling'
    ELSE 'webhook'
END
WHERE webhook_mode NOT IN ('webhook', 'polling')
   OR webhook_mode IS NULL;
