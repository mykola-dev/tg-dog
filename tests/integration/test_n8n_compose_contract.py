from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_n8n_service_contract_uses_port_50000_and_standard_first_run_setup() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_file = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "n8n:" in compose
    assert '"${N8N_PORT:-50000}:5678"' in compose
    assert "N8N_PORT=50000" in env_file
    assert "N8N_SECURE_COOKIE: false" in compose
    assert "TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}" in compose
    assert "TELEGRAM_BOT_WEBHOOK_BASE_URL: ${TELEGRAM_BOT_WEBHOOK_BASE_URL:-}" in compose
    assert "PROVIDER_TIMEOUT_SECONDS: ${PROVIDER_TIMEOUT_SECONDS:-45}" in compose
    assert "./n8n/custom-nodes:/custom-extensions:ro" in compose
    assert "./docker/n8n:/bootstrap:ro" not in compose
    assert "N8N_BOOTSTRAP_OWNER_EMAIL" not in compose
    assert "N8N_BOOTSTRAP_OWNER_PASSWORD" not in compose
    assert "OPENCODE_CONTAINER_NAME" not in env_file
    assert "api:" in compose
