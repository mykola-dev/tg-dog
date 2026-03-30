from __future__ import annotations

import getpass
import sys
from pathlib import Path

from services.shared.config import load_config
from services.shared.telegram.client import TelegramClientWrapper
from services.shared.telegram.errors import TelegramAuthError, TelegramOperationalError

MAX_CODE_RETRIES = 3
MAX_2FA_RETRIES = 3


def _prompt(label: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    full_prompt = f"{label}{suffix}:"
    while True:
        # Docker Compose multiplexes container logs line-by-line, so prompts without
        # a trailing newline can be invisible in `docker compose up` output.
        print(full_prompt, flush=True)
        if secret:
            value = getpass.getpass("").strip()
        else:
            value = input().strip()
        if not value and default:
            return default
        if value:
            return value
        print("  Value cannot be empty. Please try again.")


def _print_banner(reason: str = "No connected Telegram account found.") -> None:
    print()
    print("=== TG-Dog — Account Setup ===")
    print()
    print(f"{reason} Starting setup wizard.\n")


def _print_success(display_name: str | None) -> None:
    name_part = f' as "{display_name}"' if display_name else ""
    print(f"\nConnected{name_part}")
    print("\nSetup complete. The bot is ready.")


def _collect_credentials() -> tuple[str, str, str]:
    print("You need a Telegram API ID and API Hash from https://my.telegram.org\n")
    api_id = _prompt("Telegram API ID")
    api_hash = _prompt("Telegram API Hash")
    phone = _prompt("Phone number (with country code, e.g. +380501234567)")
    return api_id, api_hash, phone


def _submit_code_loop(client: TelegramClientWrapper, auth_flow_id: str) -> dict:
    for attempt in range(MAX_CODE_RETRIES):
        code = _prompt("Enter the login code from Telegram")
        try:
            return client.submit_code(auth_flow_id=auth_flow_id, login_code=code)
        except TelegramAuthError as exc:
            if exc.code == "INVALID_CODE" and attempt < MAX_CODE_RETRIES - 1:
                print("\nInvalid login code. Please check and try again.")
                continue
            raise
    raise TelegramAuthError(code="INVALID_CODE", message="Too many failed code attempts")


def _submit_2fa_loop(client: TelegramClientWrapper, auth_flow_id: str) -> dict:
    print("\nYour account has two-factor authentication enabled.")
    for attempt in range(MAX_2FA_RETRIES):
        password = _prompt("Enter your 2FA password", secret=True)
        try:
            return client.submit_2fa(auth_flow_id=auth_flow_id, two_factor_password=password)
        except TelegramAuthError as exc:
            if exc.code == "INVALID_2FA" and attempt < MAX_2FA_RETRIES - 1:
                print("\nInvalid 2FA password. Please try again.")
                continue
            raise
    raise TelegramAuthError(code="INVALID_2FA", message="Too many failed 2FA attempts")


def _get_display_name(response: dict) -> str | None:
    profile = response.get("account_profile")
    if profile and isinstance(profile, dict):
        return profile.get("display_name")
    return None


def run_wizard(session_path: Path, *, reason: str = "No connected Telegram account found.") -> bool:
    """Run the interactive onboarding wizard. Returns True on success, False on failure."""
    client = TelegramClientWrapper(session_path)

    _print_banner(reason)

    while True:
        api_id, api_hash, phone = _collect_credentials()

        try:
            result = client.start_login(
                api_id=api_id, api_hash=api_hash, phone_number=phone, ttl_seconds=900
            )
        except TelegramOperationalError as exc:
            print(f"\nCould not start login: {exc.message}")
            print("Check your API credentials at https://my.telegram.org and try again.\n")
            continue
        except Exception as exc:
            print(f"\nUnexpected error: {exc}")
            return False

        auth_flow_id = result["auth_flow_id"]
        masked = result.get("masked_phone_number", phone)
        print(f"\nSending login code to {masked}...")

        try:
            code_result = _submit_code_loop(client, auth_flow_id)
        except TimeoutError:
            print("\nLogin flow expired. Restarting setup...\n")
            continue
        except TelegramAuthError as exc:
            if exc.code == "AUTH_FLOW_EXPIRED":
                print("\nLogin flow expired. Restarting setup...\n")
                continue
            print(f"\nLogin failed: {exc.message}")
            return False

        if code_result["account_state"] == "connected":
            _print_success(_get_display_name(code_result))
            return True

        if code_result["account_state"] == "awaiting_2fa":
            try:
                twofa_result = _submit_2fa_loop(client, auth_flow_id)
            except TimeoutError:
                print("\nLogin flow expired. Restarting setup...\n")
                continue
            except TelegramAuthError as exc:
                if exc.code == "AUTH_FLOW_EXPIRED":
                    print("\nLogin flow expired. Restarting setup...\n")
                    continue
                print(f"\n2FA failed: {exc.message}")
                return False

            _print_success(_get_display_name(twofa_result))
            return True

        print(f"\nUnexpected account state: {code_result['account_state']}")
        return False


def main() -> None:
    """Entry point for `make connect-telegram` / `python -m services.onboarding.wizard`."""
    config = load_config(require_master_key=True)
    success = run_wizard(session_path=config.telegram_session_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
