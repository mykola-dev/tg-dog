CREATE TABLE IF NOT EXISTS telegram_trigger_subscriptions (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    webhook_mode TEXT NOT NULL DEFAULT 'production',
    dialog_id TEXT NOT NULL,
    dialog_name TEXT,
    only_incoming BOOLEAN NOT NULL DEFAULT TRUE,
    ignore_self BOOLEAN NOT NULL DEFAULT TRUE,
    ignore_service_messages BOOLEAN NOT NULL DEFAULT TRUE,
    include_media BOOLEAN NOT NULL DEFAULT TRUE,
    webhook_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workflow_id, node_id, webhook_mode)
);

ALTER TABLE telegram_trigger_subscriptions
    ADD COLUMN IF NOT EXISTS webhook_mode TEXT NOT NULL DEFAULT 'production';

DROP INDEX IF EXISTS ix_telegram_trigger_subscriptions_workflow_node;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'telegram_trigger_subscriptions_workflow_id_node_id_key'
    ) THEN
        ALTER TABLE telegram_trigger_subscriptions
            DROP CONSTRAINT telegram_trigger_subscriptions_workflow_id_node_id_key;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'telegram_trigger_subscriptions_workflow_id_node_id_webhook_mode_key'
    ) THEN
        ALTER TABLE telegram_trigger_subscriptions
            ADD CONSTRAINT telegram_trigger_subscriptions_workflow_id_node_id_webhook_mode_key
            UNIQUE (workflow_id, node_id, webhook_mode);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_telegram_trigger_subscriptions_dialog_id
    ON telegram_trigger_subscriptions (dialog_id);
