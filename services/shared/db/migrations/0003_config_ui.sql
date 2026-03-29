-- Allow API-triggered runs to omit manifest_ref
ALTER TABLE runs ALTER COLUMN manifest_ref SET DEFAULT '';

-- Add log output column to runs
ALTER TABLE runs ADD COLUMN IF NOT EXISTS log TEXT;

-- Single-row config table for the UI
CREATE TABLE IF NOT EXISTS pipeline_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    sources JSONB NOT NULL DEFAULT '[]',
    filters JSONB NOT NULL DEFAULT '{"whitelist": [], "blacklist": []}',
    scoring JSONB NOT NULL DEFAULT '{"system_prompt": "", "provider_queue": ["openai", "anthropic", "local"]}',
    delivery JSONB NOT NULL DEFAULT '{"target_id": ""}',
    schedule TEXT NOT NULL DEFAULT '',
    schedule_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed the default row so GET /config always returns something
INSERT INTO pipeline_config (id) VALUES (1) ON CONFLICT DO NOTHING;
