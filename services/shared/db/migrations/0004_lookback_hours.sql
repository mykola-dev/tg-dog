-- Add lookback_hours to pipeline_config table (default 24 hours)
ALTER TABLE pipeline_config ADD COLUMN IF NOT EXISTS lookback_hours INTEGER NOT NULL DEFAULT 24;
