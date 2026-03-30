from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_make_up_runs_foreground_with_compose_menu_disabled() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "up:" in text
    assert "docker compose up -d --build" in text
    assert "docker compose exec -it app python -m services.onboarding.ensure_connected" in text


def test_makefile_exposes_user_facing_telegram_and_reset_commands() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "connect-telegram:" in text
    assert "reset-telegram:" in text
    assert "reset-data:" in text
    assert "manifest:" not in text
    assert "onboard:" not in text
    assert "disconnect:" not in text
