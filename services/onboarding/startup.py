from __future__ import annotations

import os
import sys
from pathlib import Path

from services.shared.config import load_config
from services.shared.telegram.client import TelegramClientWrapper
from services.onboarding.wizard import run_wizard


def _is_tty() -> bool:
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


def check_and_onboard() -> bool:
    """Check auth state and run wizard if needed. Returns True if connected."""
    config = load_config(require_master_key=True)
    session_path = config.telegram_session_path
    client = TelegramClientWrapper(session_path)

    try:
        status = client.status()
    except Exception:
        status = {"account_state": "disconnected"}

    account_state = status.get("account_state", "disconnected")
    profile = status.get("account_profile")
    display_name = profile.get("display_name") if isinstance(profile, dict) else None

    if account_state == "connected":
        name_part = f" ({display_name})" if display_name else ""
        print(f"Telegram account connected{name_part}. Skipping setup.")
        return True

    if account_state == "reauth_required":
        reason = "Previously stored credentials are no longer valid."
    else:
        reason = "No connected Telegram account found."

    if not _is_tty():
        print(reason)
        print("Run 'make onboard' to complete setup.")
        return False

    return run_wizard(session_path=session_path, reason=reason)


def main() -> None:
    """Container entrypoint. Runs onboard check, then exec's into sleep."""
    check_and_onboard()
    # Replace this process with sleep infinity so the container stays alive
    os.execvp("sleep", ["sleep", "infinity"])


if __name__ == "__main__":
    main()
