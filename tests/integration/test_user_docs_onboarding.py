from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _assert_in_order(text: str, snippets: list[str]) -> None:
    positions = [text.index(snippet) for snippet in snippets]
    assert positions == sorted(positions)


def _section(text: str, heading: str, next_heading: str | None = None) -> str:
    start = text.index(heading)
    end = text.index(next_heading, start) if next_heading else len(text)
    return text[start:end]
def test_telegram_app_setup_doc_is_beginner_proof() -> None:
    text = _text("docs/user/telegram-app-setup.md")
    for expected in [
        "What this is for",
        "Before you start",
        "Fill in the application form",
        "- **App title:**",
        "- **Short name:**",
        "- **URL:**",
        "- **Platform:**",
        "- **Description:**",
        "Confirmed for this project",
        "Observed Telegram portal behavior (2026-03-22)",
        "incorrect app title",
        "api_id",
        "api_hash",
    ]:
        assert expected in text


def test_telegram_app_setup_doc_contains_fallback_sequence() -> None:
    text = _text("docs/user/telegram-app-setup.md")
    for expected in [
        "letters and digits only",
        "lowercase letters and digits only",
        "remove decorative punctuation",
        "brand-like words",
        "fresh browser session or private/incognito window",
        "Disable ad blockers",
        "If Telegram currently requires a `URL`",
    ]:
        assert expected in text


def test_connect_account_doc_describes_cli_wizard() -> None:
    text = _text("docs/user/connect-account.md")
    for expected in [
        "make up",
        "setup wizard",
        "Telegram API ID",
        "Telegram API Hash",
        "Phone number",
        "login code",
        "Connected",
    ]:
        assert expected in text


def test_connect_account_doc_explains_reuse_and_re_setup() -> None:
    text = _text("docs/user/connect-account.md")
    assert "Subsequent runs" in text
    assert "Skipping setup" in text
    assert "make connect-telegram" in text
    assert "make reset-telegram" in text


def test_connect_account_doc_covers_detached_mode() -> None:
    text = _text("docs/user/connect-account.md")
    assert "Detached mode" in text or "detached" in text
    assert "docker compose up -d" in text
    assert "make connect-telegram" in text


def test_connect_account_doc_lists_common_errors() -> None:
    text = _text("docs/user/connect-account.md")
    for expected in [
        "Invalid login code",
        "Invalid 2FA password",
        "Login flow expired",
    ]:
        assert expected in text


def test_troubleshooting_doc_splits_portal_and_workflow_issues() -> None:
    text = _text("docs/user/troubleshooting.md")
    for expected in [
        "Auth issues",
        "AUTH_FLOW_EXPIRED",
        "reauth_required",
        "The stack no longer imports repo-managed workflows on startup",
    ]:
        assert expected in text


def test_quickstart_points_to_setup_then_connect_then_first_digest() -> None:
    text = _text("docs/user/quickstart.md")
    assert "docs/user/telegram-app-setup.md" in text
    assert "docs/user/connect-account.md" in text
    assert text.index("docs/user/telegram-app-setup.md") < text.index("docs/user/connect-account.md")
    assert "## 5) Connect Telegram account" in text
    assert "Run first digest" in text or "run first digest" in text.lower()
