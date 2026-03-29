CREATE TABLE IF NOT EXISTS installation_settings (
    key VARCHAR(128) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS account_state (
    id SERIAL PRIMARY KEY,
    account_state VARCHAR(64) NOT NULL,
    account_profile JSONB,
    last_successful_auth_at TIMESTAMPTZ,
    last_auth_error JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_configuration (
    source_ref VARCHAR(255) PRIMARY KEY,
    source_kind VARCHAR(32) NOT NULL,
    source_title VARCHAR(512) NOT NULL,
    include BOOLEAN NOT NULL DEFAULT TRUE,
    exclude BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS node_toggles (
    node_name VARCHAR(64) PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS filter_rules (
    rule_id VARCHAR(64) PRIMARY KEY,
    rule_type VARCHAR(32) NOT NULL,
    name VARCHAR(255) NOT NULL,
    config JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR(64) PRIMARY KEY,
    trigger_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    manifest_ref VARCHAR(512) NOT NULL
);

CREATE TABLE IF NOT EXISTS run_outputs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    node_name VARCHAR(64) NOT NULL,
    artifact_ref VARCHAR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scheduled_cursor_state (
    id SERIAL PRIMARY KEY,
    cursor_key VARCHAR(255) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS delivery_receipts (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    delivery_status VARCHAR(64) NOT NULL,
    digest_fingerprint VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    sent_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
