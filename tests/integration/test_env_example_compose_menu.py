from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_env_example_disables_compose_menu_for_interactive_wizard() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "COMPOSE_MENU=false" in text
    assert "N8N_PASSWORD=" in text
    assert "N8N_PORT=50000" in text
    assert "TELEGRAM_BOT_WEBHOOK_BASE_URL=" in text
    assert "OPENCODE_CONTAINER_NAME=" in text
    assert "OPENCODE_COMMAND_TEMPLATE=" in text
    assert "PROVIDER_TIMEOUT_SECONDS=" in text
