from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

import services.delivery.main as delivery_main
from services.shared.telegram.client import TelegramClientWrapper
from services.shared.telegram.errors import TelegramDeliveryError


ROOT = Path(__file__).resolve().parents[2]


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


class AlwaysRetryableFailureSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, self_wrapper: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        self.calls.append((target_id, chunk_text))
        raise TelegramDeliveryError(
            code="RATE_LIMIT",
            message="deterministic wrapper boundary failure",
            retryable=True,
        )


def _patch_sender(monkeypatch: pytest.MonkeyPatch, sender: AlwaysRetryableFailureSender) -> None:
    def fake_send_text_chunk(
        self_wrapper: TelegramClientWrapper,
        *,
        target_id: str,
        chunk_text: str,
    ) -> dict[str, str]:
        return sender(self_wrapper, target_id=target_id, chunk_text=chunk_text)

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)


def _write_digest(workspace: Path, run_id: str, fingerprint: str = "fp-retry") -> str:
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    digest = {
        "digest_fingerprint": fingerprint,
        "sections": [],
        "message_count_summary": {"total": 4},
        "rendered_text_plain": "retry test",
        "delivery_chunks": ["c1", "c2", "c3", "c4"],
    }
    ref = f"runs/{run_id}/digest.json"
    (workspace / ref).write_text(json.dumps(digest), encoding="utf-8")
    return ref


def test_retryable_delivery_failure_stops_after_three_attempts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = ROOT / ".pytest_runtime" / "retry_backoff"
    shutil.rmtree(runtime, ignore_errors=True)
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    workspace.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    _configure_delivery_runtime(monkeypatch, workspace, sessions)

    digest_ref = _write_digest(workspace, "retry-run")
    sender = AlwaysRetryableFailureSender()
    _patch_sender(monkeypatch, sender)

    envelope, exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="retry-run",
        digest_ref=digest_ref,
        target_id="self",
    )

    assert exit_code is None
    delivery = json.loads((workspace / envelope["payload_ref"]).read_text(encoding="utf-8"))
    assert delivery["delivery_status"] == "failed"
    assert delivery["retry_attempts"] == 3
    assert delivery["sent_message_refs"] == []
    assert sender.calls == [("self", "c1"), ("self", "c1"), ("self", "c1")]


def test_repeated_identical_error_enters_cooldown(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = ROOT / ".pytest_runtime" / "retry_cooldown"
    shutil.rmtree(runtime, ignore_errors=True)
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    workspace.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    _configure_delivery_runtime(monkeypatch, workspace, sessions)

    digest_ref = _write_digest(workspace, "cooldown-run", fingerprint="fp-cooldown")
    sender = AlwaysRetryableFailureSender()
    _patch_sender(monkeypatch, sender)

    first, first_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="cooldown-run-1",
        digest_ref=digest_ref,
        target_id="self",
    )
    first_delivery = json.loads((workspace / first["payload_ref"]).read_text(encoding="utf-8"))

    second, second_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="cooldown-run-2",
        digest_ref=digest_ref,
        target_id="self",
    )
    second_delivery = json.loads((workspace / second["payload_ref"]).read_text(encoding="utf-8"))

    third, exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="cooldown-run-3",
        digest_ref=digest_ref,
        target_id="self",
    )

    assert first_exit_code is None
    assert first_delivery["delivery_status"] == "failed"
    assert second_exit_code is None
    assert second_delivery["delivery_status"] == "blocked_safety_policy"
    assert exit_code is None
    delivery = json.loads((workspace / third["payload_ref"]).read_text(encoding="utf-8"))
    assert delivery["delivery_status"] == "blocked_safety_policy"
    assert delivery["system_status"] == "delivery paused"
