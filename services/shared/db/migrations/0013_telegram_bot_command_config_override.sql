ALTER TABLE telegram_bot_command_config
    ADD COLUMN IF NOT EXISTS override_enabled BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE telegram_bot_command_config
SET override_enabled = CASE
    WHEN webhook_mode = 'polling' THEN TRUE
    WHEN COALESCE(webhook_base_url, '') <> '' THEN TRUE
    ELSE FALSE
END
WHERE override_enabled IS DISTINCT FROM CASE
    WHEN webhook_mode = 'polling' THEN TRUE
    WHEN COALESCE(webhook_base_url, '') <> '' THEN TRUE
    ELSE FALSE
END;
