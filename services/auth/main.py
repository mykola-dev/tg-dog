from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from services.shared.cli import build_error_envelope, build_success_envelope, emit_envelope
from services.shared.config import ConfigError, load_config
from services.shared.contracts.auth import (
    AuthErrorCode,
    AuthStartLoginRequest,
    AuthStartLoginResponse,
    AuthStatusResponse,
    AuthSubmit2FARequest,
    AuthSubmit2FAResponse,
    AuthSubmitCodeRequest,
    AuthSubmitCodeResponse,
    get_auth_workflow_error,
)
from services.shared.telegram.errors import TelegramAuthError, TelegramOperationalError
from services.shared.telegram.client import TelegramClientWrapper


def _is_digest_action_allowed(account_state: str) -> bool:
    return account_state not in {"disconnected", "reauth_required"}


def _clear_runtime_state(workspace_path: Path) -> None:
    if not workspace_path.exists():
        return
    for child in workspace_path.iterdir():
        if child.is_file():
            child.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auth adapter")
    parser.add_argument(
        "command",
        choices=["start-login", "submit-code", "submit-2fa", "status", "disconnect", "reset-account"],
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--payload-json", default="{}")
    return parser.parse_args()


def _parse_payload(raw: str) -> dict:
    return json.loads(raw)


def _emit_auth_workflow_error(*, run_id: str, code: AuthErrorCode) -> None:
    typed = get_auth_workflow_error(code)
    emit_envelope(
        build_error_envelope(
            node_name="auth",
            run_id=run_id,
            code=typed.code,
            message=typed.message,
            retryable=typed.retryable,
            user_action_required=typed.user_action_required,
            recommended_action=typed.recommended_action,
        )
    )


def main() -> None:
    args = parse_args()
    run_id = args.run_id

    try:
        config = load_config(require_master_key=True)
    except ConfigError as exc:
        emit_envelope(
            build_error_envelope(
                node_name="auth",
                run_id=run_id,
                code="AUTH_CONFIG_ERROR",
                message=str(exc),
                retryable=False,
                user_action_required=True,
            )
        )
        sys.exit(1)

    payload = _parse_payload(args.payload_json)
    client = TelegramClientWrapper(config.telegram_session_path)

    try:
        if args.command == "start-login":
            request = AuthStartLoginRequest.model_validate(payload)
            ttl = int(payload.get("auth_flow_ttl_seconds", 900))
            response = client.start_login(
                api_id=request.api_id,
                api_hash=request.api_hash,
                phone_number=request.phone_number,
                ttl_seconds=ttl,
            )
            typed = AuthStartLoginResponse.model_validate(response)
            emit_envelope(
                build_success_envelope(
                    node_name="auth",
                    run_id=run_id,
                    payload_inline=typed.model_dump(mode="json"),
                )
            )
            return

        if args.command == "submit-code":
            request = AuthSubmitCodeRequest.model_validate(payload)
            response = client.submit_code(
                auth_flow_id=request.auth_flow_id,
                login_code=request.login_code,
            )
            typed = AuthSubmitCodeResponse.model_validate(response)
            emit_envelope(
                build_success_envelope(
                    node_name="auth",
                    run_id=run_id,
                    payload_inline=typed.model_dump(mode="json"),
                )
            )
            return

        if args.command == "submit-2fa":
            request = AuthSubmit2FARequest.model_validate(payload)
            response = client.submit_2fa(
                auth_flow_id=request.auth_flow_id,
                two_factor_password=request.two_factor_password,
            )
            typed = AuthSubmit2FAResponse.model_validate(response)
            emit_envelope(
                build_success_envelope(
                    node_name="auth",
                    run_id=run_id,
                    payload_inline=typed.model_dump(mode="json"),
                )
            )
            return

        if args.command == "status":
            typed = AuthStatusResponse.model_validate(client.status())
            emit_envelope(
                build_success_envelope(
                    node_name="auth",
                    run_id=run_id,
                    payload_inline=typed.model_dump(mode="json"),
                )
            )
            return

        if args.command == "disconnect":
            response = client.disconnect()
            emit_envelope(
                build_success_envelope(
                    node_name="auth",
                    run_id=run_id,
                    payload_inline=response,
                )
            )
            return

        if args.command == "reset-account":
            response = client.reset_account()
            _clear_runtime_state(config.workspace_path)
            emit_envelope(
                build_success_envelope(
                    node_name="auth",
                    run_id=run_id,
                    payload_inline=response,
                )
            )
            return
    except TimeoutError:
        _emit_auth_workflow_error(run_id=run_id, code="AUTH_FLOW_EXPIRED")
        sys.exit(1)
    except TelegramAuthError as exc:
        workflow_code: AuthErrorCode | None = None
        if exc.code == "AUTH_FLOW_NOT_FOUND":
            workflow_code = "AUTH_FLOW_NOT_FOUND"
        elif exc.code == "INVALID_CODE":
            workflow_code = "INVALID_CODE"
        elif exc.code == "INVALID_2FA":
            workflow_code = "INVALID_2FA"

        if workflow_code is not None:
            _emit_auth_workflow_error(run_id=run_id, code=workflow_code)
        else:
            emit_envelope(
                build_error_envelope(
                    node_name="auth",
                    run_id=run_id,
                    code=exc.code,
                    message="Authentication request failed",
                    retryable=False,
                    user_action_required=True,
                )
            )
        sys.exit(1)
    except TelegramOperationalError as exc:
        emit_envelope(
            build_error_envelope(
                node_name="auth",
                run_id=run_id,
                code=exc.code,
                message=exc.message,
                retryable=False,
                user_action_required=True,
            )
        )
        sys.exit(1)
    except Exception as exc:  # pragma: no cover
        emit_envelope(
            build_error_envelope(
                node_name="auth",
                run_id=run_id,
                code="AUTH_UNEXPECTED",
                message=str(exc),
                retryable=True,
                user_action_required=False,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
