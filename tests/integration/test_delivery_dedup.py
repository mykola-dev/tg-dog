from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import services.delivery.main as delivery_main
from services.shared.runtime.idempotency import DeliveryDedupStore
from services.shared.telegram.client import TelegramClientWrapper, _legacy_encrypt_secret
from services.shared.telegram.errors import TelegramDeliveryError


def _configure_delivery_runtime(
    monkeypatch: pytest.MonkeyPatch,
    workspace: Path,
    sessions: Path,
) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "telegram_digest")
    monkeypatch.setenv("POSTGRES_USER", "telegram_digest")
    monkeypatch.setenv("POSTGRES_PASSWORD", "telegram_digest")
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(sessions))
    monkeypatch.setenv("APP_TIMEZONE", "UTC")
    monkeypatch.setenv("APP_MASTER_KEY", "test_master_key")


def _invoke_delivery_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    run_id: str,
    digest_ref: str,
    target_id: str,
    resume: str = "false",
) -> tuple[dict[str, Any], int | None]:
    monkeypatch.setattr(
        "sys.argv",
        [
            "services.delivery.main",
            "--run-id",
            run_id,
            "--digest-ref",
            digest_ref,
            "--target-id",
            target_id,
            "--resume",
            resume,
        ],
    )

    exit_code: int | None = None
    try:
        delivery_main.main()
    except SystemExit as exc:
        raw_code: object = exc.code
        if isinstance(raw_code, int):
            exit_code = raw_code
        elif raw_code is None:
            exit_code = 0
        else:
            exit_code = int(str(raw_code))

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    return payload, exit_code


def _authenticate_wrapper_in_test_mode(sessions: Path) -> None:
    """Seed auth state directly to avoid real Telethon network calls in delivery tests."""
    wrapper = TelegramClientWrapper(sessions)
    wrapper.state_file.write_text(
        json.dumps(
            {
                "account_state": "connected",
                "last_successful_auth_at": "2026-01-01T00:00:00+00:00",
                "last_auth_error": None,
                "api_id": "1",
                "api_hash_encrypted": _legacy_encrypt_secret("hash"),
                "account_profile": {"display_name": "Test User"},
            }
        ),
        encoding="utf-8",
    )


class PartialFailureSender:
    def __init__(self, *, fail_on_call: int) -> None:
        self.fail_on_call = fail_on_call
        self.calls: list[tuple[str, str]] = []

    def __call__(self, self_wrapper: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        self.calls.append((target_id, chunk_text))
        if len(self.calls) >= self.fail_on_call:
            raise TelegramDeliveryError(
                code="RATE_LIMIT",
                message="deterministic partial send failure",
                retryable=True,
            )
        return {
            "chat_id": "me",
            "message_id": str(9000 + len(self.calls)),
        }


class SuccessfulSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, self_wrapper: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        self.calls.append((target_id, chunk_text))
        return {
            "chat_id": "me",
            "message_id": str(9100 + len(self.calls)),
        }


def _patch_sender(
    monkeypatch: pytest.MonkeyPatch,
    sender: PartialFailureSender | SuccessfulSender,
) -> None:
    def fake_send_text_chunk(
        self_wrapper: TelegramClientWrapper,
        *,
        target_id: str,
        chunk_text: str,
    ) -> dict[str, str]:
        return sender(self_wrapper, target_id=target_id, chunk_text=chunk_text)

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)


def _write_digest(workspace: Path, run_id: str, fingerprint: str = "fp-dedup") -> str:
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    digest = {
        "digest_fingerprint": fingerprint,
        "sections": [],
        "message_count_summary": {"total": 4},
        "rendered_text_plain": "dedup test",
        "delivery_chunks": ["c1", "c2", "c3", "c4"],
    }
    ref = f"runs/{run_id}/digest.json"
    (workspace / ref).write_text(json.dumps(digest), encoding="utf-8")
    return ref


def test_partial_delivery_resume_safe_dedup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = tmp_path / "delivery_dedup_resume"
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    workspace.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    _configure_delivery_runtime(monkeypatch, workspace, sessions)
    _authenticate_wrapper_in_test_mode(sessions)

    digest_ref = _write_digest(workspace, "dedup-resume-run", fingerprint="fp-resume")
    first_sender = PartialFailureSender(fail_on_call=3)
    _patch_sender(monkeypatch, first_sender)

    first_env, first_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="dedup-resume-run",
        digest_ref=digest_ref,
        target_id="self",
    )
    assert first_exit_code is None
    first_delivery = json.loads((workspace / first_env["payload_ref"]).read_text(encoding="utf-8"))
    assert first_delivery["delivery_status"] == "failed"
    assert len(first_delivery["sent_message_refs"]) == 2
    assert DeliveryDedupStore(workspace).get_sent_count("fp-resume") == 2

    second_sender = SuccessfulSender()
    _patch_sender(monkeypatch, second_sender)

    second_env, second_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="dedup-resume-run",
        digest_ref=digest_ref,
        target_id="self",
        resume="true",
    )
    assert second_exit_code is None
    second_delivery = json.loads((workspace / second_env["payload_ref"]).read_text(encoding="utf-8"))
    assert second_delivery["delivery_status"] == "sent"
    assert len(second_delivery["sent_message_refs"]) == 4
    assert second_delivery["sent_message_refs"] == [
        {"chat_id": "me", "message_id": "9001"},
        {"chat_id": "me", "message_id": "9002"},
        {"chat_id": "me", "message_id": "9101"},
        {"chat_id": "me", "message_id": "9102"},
    ]
    assert first_sender.calls == [
        ("self", "c1"),
        ("self", "c2"),
        ("self", "c3"),
        ("self", "c3"),
        ("self", "c3"),
    ]
    assert second_sender.calls == [("self", "c3"), ("self", "c4")]
    assert DeliveryDedupStore(workspace).get_sent_count("fp-resume") == 0

    duplicate_env, duplicate_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="dedup-resume-run-duplicate",
        digest_ref=digest_ref,
        target_id="self",
    )
    assert duplicate_exit_code is None
    duplicate_delivery = json.loads((workspace / duplicate_env["payload_ref"]).read_text(encoding="utf-8"))
    assert duplicate_delivery["delivery_status"] == "skipped_duplicate"


def test_duplicate_identical_digest_attempt_is_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = tmp_path / "delivery_dedup_skip"
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    workspace.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    _configure_delivery_runtime(monkeypatch, workspace, sessions)
    _authenticate_wrapper_in_test_mode(sessions)

    digest_ref = _write_digest(workspace, "dedup-skip-run", fingerprint="fp-skip")
    sender = SuccessfulSender()
    _patch_sender(monkeypatch, sender)

    first_env, first_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="dedup-skip-run-1",
        digest_ref=digest_ref,
        target_id="self",
    )
    assert first_exit_code is None
    first_delivery = json.loads((workspace / first_env["payload_ref"]).read_text(encoding="utf-8"))
    assert first_delivery["delivery_status"] == "sent"

    second_env, second_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="dedup-skip-run-2",
        digest_ref=digest_ref,
        target_id="self",
    )
    assert second_exit_code is None
    second_delivery = json.loads((workspace / second_env["payload_ref"]).read_text(encoding="utf-8"))
    assert second_delivery["delivery_status"] == "skipped_duplicate"
    assert sender.calls == [("self", "c1"), ("self", "c2"), ("self", "c3"), ("self", "c4")]
