import json
from pathlib import Path
from typing import Any

import pytest

import services.delivery.main as delivery_main
import services.shared.telegram.client as telegram_client_module
from services.shared.runtime.idempotency import DeliveryDedupStore
from services.shared.telegram.client import TelegramClientWrapper, _legacy_encrypt_secret
from services.shared.telegram.errors import TelegramDeliveryError


def _authenticate_wrapper_in_test_mode(wrapper: TelegramClientWrapper) -> None:
    """Seed auth state directly to avoid real Telethon network calls in delivery tests."""
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


def _configure_delivery_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, run_id: str) -> tuple[Path, Path]:
    runtime = tmp_path / "delivery_cli"
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "telegram_digest")
    monkeypatch.setenv("POSTGRES_USER", "telegram_digest")
    monkeypatch.setenv("POSTGRES_PASSWORD", "telegram_digest")
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(sessions))
    monkeypatch.setenv("APP_TIMEZONE", "UTC")
    monkeypatch.setenv("APP_MASTER_KEY", "test_master_key")

    return workspace, run_dir


def _write_digest(run_dir: Path, *, fingerprint: str, chunks: list[str]) -> None:
    digest = {
        "digest_fingerprint": fingerprint,
        "sections": [],
        "message_count_summary": {"total": len(chunks)},
        "rendered_text_plain": "text",
        "delivery_chunks": chunks,
    }
    (run_dir / "digest.json").write_text(json.dumps(digest), encoding="utf-8")


def _invoke_delivery_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    run_id: str,
    target_id: str,
    resume: str = "false",
    digest_ref: str | None = None,
) -> tuple[dict[str, Any], int | None]:
    monkeypatch.setattr(
        "sys.argv",
        [
            "services.delivery.main",
            "--run-id",
            run_id,
            "--digest-ref",
            digest_ref or f"runs/{run_id}/digest.json",
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


def test_wrapper_send_succeeds_after_submit_code_persists_connected_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    _authenticate_wrapper_in_test_mode(wrapper)

    persisted_state = wrapper._load_json(wrapper.state_file)

    async def fake_send(
        *,
        api_id: str,
        api_hash: str,
        target_id: str,
        chunk_text: str,
        parse_mode: str = "plain_text",
        media_file_ref: str | None = None,
        media_mime_type: str | None = None,
        media_kind: str | None = None,
    ) -> dict[str, str]:
        return {"chat_id": "me", "message_id": "42"}

    monkeypatch.setattr(wrapper, "_async_send_text_chunk", fake_send, raising=False)

    result = wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert persisted_state["account_state"] == "connected"
    assert persisted_state["api_id"] == "1"
    assert persisted_state["api_hash_encrypted"] == _legacy_encrypt_secret("hash")
    assert result == {"chat_id": "me", "message_id": "42"}


def test_wrapper_repost_message_uses_async_repost_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    _authenticate_wrapper_in_test_mode(wrapper)

    async def fake_repost(
        *,
        api_id: str,
        api_hash: str,
        target_id: str,
        source_id: str,
        source_message_id: str,
        mode: str,
    ) -> dict[str, str]:
        assert api_id == "1"
        assert api_hash == "hash"
        assert target_id == "self"
        assert source_id == "-100123"
        assert source_message_id == "42"
        assert mode == "copy"
        return {"chat_id": "me", "message_id": "77"}

    monkeypatch.setattr(wrapper, "_async_repost_message", fake_repost, raising=False)

    result = wrapper.repost_message(
        target_id="self",
        source_id="-100123",
        source_message_id="42",
        mode="copy",
    )

    assert result == {"chat_id": "me", "message_id": "77"}


def test_wrapper_repost_message_rejects_unsupported_mode(tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path)

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.repost_message(
            target_id="self",
            source_id="-100123",
            source_message_id="42",
            mode="send",
        )

    assert exc_info.value.code == "POST_DELIVERY_MODE_UNSUPPORTED"


def test_wrapper_normalizes_missing_delivery_target_to_typed_error(tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    _authenticate_wrapper_in_test_mode(wrapper)

    assert hasattr(wrapper, "send_text_chunk")

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="chat-123", chunk_text="hello")

    assert exc_info.value.code in {"DELIVERY_TARGET_NOT_FOUND", "AUTH_REQUIRED", "DELIVERY_SEND_FAILED"}
    assert exc_info.value.retryable is False


def test_wrapper_requires_connected_session_for_delivery_when_state_missing(tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path)

    assert hasattr(wrapper, "send_text_chunk")

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.retryable is False


def test_wrapper_requires_connected_session_for_delivery_when_persisted_state_is_disconnected(tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    wrapper.state_file.write_text(
        json.dumps(
            {
                "account_state": "disconnected",
                "last_successful_auth_at": None,
                "last_auth_error": None,
                "account_profile": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.retryable is False


def test_wrapper_normalizes_rate_limit_delivery_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeFloodWaitError(Exception):
        pass

    wrapper = TelegramClientWrapper(tmp_path)
    _authenticate_wrapper_in_test_mode(wrapper)

    async def fake_send(
        *,
        api_id: str,
        api_hash: str,
        target_id: str,
        chunk_text: str,
        parse_mode: str = "plain_text",
        media_file_ref: str | None = None,
        media_mime_type: str | None = None,
        media_kind: str | None = None,
    ) -> dict[str, str]:
        raise FakeFloodWaitError("A wait of 30 seconds is required due to rate limit")

    assert hasattr(wrapper, "send_text_chunk")
    monkeypatch.setattr(wrapper, "_async_send_text_chunk", fake_send, raising=False)

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "RATE_LIMIT"
    assert exc_info.value.retryable is True


def test_wrapper_normalizes_generic_retryable_delivery_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    _authenticate_wrapper_in_test_mode(wrapper)

    async def fake_send(
        *,
        api_id: str,
        api_hash: str,
        target_id: str,
        chunk_text: str,
        parse_mode: str = "plain_text",
        media_file_ref: str | None = None,
        media_mime_type: str | None = None,
        media_kind: str | None = None,
    ) -> dict[str, str]:
        raise RuntimeError("temporary send failure")

    assert hasattr(wrapper, "send_text_chunk")
    monkeypatch.setattr(wrapper, "_async_send_text_chunk", fake_send, raising=False)

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "DELIVERY_SEND_FAILED"
    assert exc_info.value.retryable is True


def test_wrapper_keeps_generic_failures_as_delivery_send_failed_when_wait_classes_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    _authenticate_wrapper_in_test_mode(wrapper)

    async def fake_send(
        *,
        api_id: str,
        api_hash: str,
        target_id: str,
        chunk_text: str,
        parse_mode: str = "plain_text",
        media_file_ref: str | None = None,
        media_mime_type: str | None = None,
        media_kind: str | None = None,
    ) -> dict[str, str]:
        raise RuntimeError("temporary send failure")

    monkeypatch.setattr(telegram_client_module, "FloodWaitError", Exception)
    monkeypatch.setattr(telegram_client_module, "SlowModeWaitError", Exception)
    monkeypatch.setattr(wrapper, "_async_send_text_chunk", fake_send, raising=False)

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "DELIVERY_SEND_FAILED"
    assert exc_info.value.retryable is True


def test_wrapper_returns_typed_auth_error_for_malformed_persisted_auth_state(tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    wrapper.state_file.write_text(
        json.dumps(
            {
                "account_state": "connected",
                "api_id": "1",
                "api_hash_encrypted": "not-encrypted",
                "account_profile": {"display_name": "Connected User"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.retryable is False


def test_wrapper_returns_typed_auth_error_for_invalid_persisted_api_id(tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    wrapper.state_file.write_text(
        json.dumps(
            {
                "account_state": "connected",
                "api_id": "not-an-int",
                "api_hash_encrypted": _legacy_encrypt_secret("hash"),
                "account_profile": {"display_name": "Connected User"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.retryable is False


def test_wrapper_returns_typed_auth_error_for_malformed_auth_state_json(tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    wrapper.state_file.write_text("{not-json", encoding="utf-8")

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.retryable is False


@pytest.mark.parametrize("persisted_state", [[], None, "x"])
def test_wrapper_returns_typed_auth_error_for_wrong_shape_auth_state(
    tmp_path: Path,
    persisted_state: object,
) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    wrapper.state_file.write_text(json.dumps(persisted_state), encoding="utf-8")

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.retryable is False


def test_wrapper_normalizes_auth_like_send_failures_to_auth_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAuthKeyUnregisteredError(Exception):
        pass

    wrapper = TelegramClientWrapper(tmp_path)
    _authenticate_wrapper_in_test_mode(wrapper)

    async def fake_send(
        *,
        api_id: str,
        api_hash: str,
        target_id: str,
        chunk_text: str,
        parse_mode: str = "plain_text",
        media_file_ref: str | None = None,
        media_mime_type: str | None = None,
        media_kind: str | None = None,
    ) -> dict[str, str]:
        raise FakeAuthKeyUnregisteredError("AUTH_KEY_UNREGISTERED")

    monkeypatch.setattr(wrapper, "_async_send_text_chunk", fake_send, raising=False)

    with pytest.raises(TelegramDeliveryError) as exc_info:
        wrapper.send_text_chunk(target_id="self", chunk_text="hello")

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.retryable is False


def test_delivery_cli_uses_wrapper_returned_message_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, run_dir = _configure_delivery_runtime(monkeypatch, tmp_path, run_id="delivery-run")
    _write_digest(run_dir, fingerprint="fp-wrapper", chunks=["chunk-1", "chunk-2"])

    returned_refs = [
        {"chat_id": "chat-from-wrapper", "message_id": "9001"},
        {"chat_id": "chat-from-wrapper", "message_id": "9002"},
    ]
    calls: list[tuple[str, str]] = []

    def fake_send_text_chunk(self: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        calls.append((target_id, chunk_text))
        return returned_refs[len(calls) - 1]

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)

    payload, exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="delivery-run",
        target_id="self",
    )

    assert exit_code is None
    assert payload["status"] == "ok"
    assert calls == [("self", "chunk-1"), ("self", "chunk-2")]
    receipt = json.loads((workspace / str(payload["payload_ref"])).read_text(encoding="utf-8"))
    assert receipt["sent_message_refs"] == returned_refs


def test_delivery_cli_rejects_unsupported_target_explicitly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, run_dir = _configure_delivery_runtime(monkeypatch, tmp_path, run_id="delivery-run")
    _write_digest(run_dir, fingerprint="fp-unsupported", chunks=["chunk-1"])

    payload, exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="delivery-run",
        target_id="not-self",
    )
    error = payload.get("error")

    assert exit_code == 1
    assert payload["status"] == "error"
    assert isinstance(error, dict)
    assert error["code"] == "UNSUPPORTED_DELIVERY_TARGET"


def test_delivery_cli_returns_structured_auth_error_when_wrapper_requires_reauth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, run_dir = _configure_delivery_runtime(monkeypatch, tmp_path, run_id="delivery-run")
    _write_digest(run_dir, fingerprint="fp-auth", chunks=["chunk-1"])

    def fake_send_text_chunk(self: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        raise TelegramDeliveryError(
            code="AUTH_REQUIRED",
            message="Telegram authorization is required before delivery",
            retryable=False,
        )

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)

    payload, exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="delivery-run",
        target_id="self",
    )
    error = payload.get("error")

    assert exit_code == 1
    assert payload["status"] == "error"
    assert isinstance(error, dict)
    assert error["code"] == "AUTH_REQUIRED"
    assert error["user_action_required"] is True


def test_delivery_cli_persists_partial_progress_when_later_chunk_hits_auth_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, run_dir = _configure_delivery_runtime(monkeypatch, tmp_path, run_id="delivery-run")
    _write_digest(run_dir, fingerprint="fp-auth-partial", chunks=["chunk-1", "chunk-2", "chunk-3"])

    def fake_send_text_chunk(self: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        if chunk_text == "chunk-1":
            return {"chat_id": "me", "message_id": "41"}
        raise TelegramDeliveryError(
            code="AUTH_REQUIRED",
            message="Telegram authorization is required before delivery",
            retryable=False,
        )

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)

    payload, exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="delivery-run",
        target_id="self",
    )
    error = payload.get("error")

    assert exit_code == 1
    assert payload["status"] == "error"
    assert isinstance(error, dict)
    assert error["code"] == "AUTH_REQUIRED"
    assert DeliveryDedupStore(workspace).get_sent_count("fp-auth-partial") == 1


def test_delivery_cli_writes_failure_receipt_when_later_chunk_hits_auth_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, run_dir = _configure_delivery_runtime(monkeypatch, tmp_path, run_id="delivery-run")
    _write_digest(run_dir, fingerprint="fp-auth-artifact", chunks=["chunk-1", "chunk-2", "chunk-3"])

    def fake_send_text_chunk(self: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        if chunk_text == "chunk-1":
            return {"chat_id": "me", "message_id": "41"}
        raise TelegramDeliveryError(
            code="AUTH_REQUIRED",
            message="Telegram authorization is required before delivery",
            retryable=False,
        )

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)

    payload, exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="delivery-run",
        target_id="self",
    )
    error = payload.get("error")
    receipt_path = workspace / "runs" / "delivery-run" / "delivery.json"

    assert exit_code == 1
    assert payload["status"] == "error"
    assert isinstance(error, dict)
    assert error["code"] == "AUTH_REQUIRED"
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["delivery_status"] == "failed"
    assert receipt["sent_message_refs"] == [{"chat_id": "me", "message_id": "41"}]


def test_delivery_cli_persists_partial_progress_when_later_chunk_fails_retryably(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, run_dir = _configure_delivery_runtime(monkeypatch, tmp_path, run_id="delivery-run")
    _write_digest(run_dir, fingerprint="fp-partial", chunks=["chunk-1", "chunk-2", "chunk-3"])

    def fake_send_text_chunk(self: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        if chunk_text == "chunk-1":
            return {"chat_id": "me", "message_id": "41"}
        raise TelegramDeliveryError(
            code="RATE_LIMIT",
            message="Telegram rate limit encountered during delivery",
            retryable=True,
        )

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)

    payload, exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="delivery-run",
        target_id="self",
    )

    assert exit_code is None
    assert payload["status"] == "ok"
    receipt = json.loads((workspace / str(payload["payload_ref"])).read_text(encoding="utf-8"))
    assert receipt["delivery_status"] == "failed"
    assert receipt["sent_message_refs"] == [{"chat_id": "me", "message_id": "41"}]
    assert DeliveryDedupStore(workspace).get_sent_count("fp-partial") == 1


def test_delivery_truncation_preserves_order_and_adds_notice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, run_dir = _configure_delivery_runtime(monkeypatch, tmp_path, run_id="delivery-run")
    _write_digest(run_dir, fingerprint="fp1", chunks=[f"chunk-{i}" for i in range(1, 10)])

    sent_chunks: list[str] = []

    def fake_send_text_chunk(self: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        sent_chunks.append(chunk_text)
        return {"chat_id": "me", "message_id": str(len(sent_chunks))}

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)

    payload, exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="delivery-run",
        target_id="self",
    )

    assert exit_code is None
    assert payload["status"] == "ok"
    receipt = json.loads((workspace / str(payload["payload_ref"])).read_text(encoding="utf-8"))
    assert len(receipt["sent_message_refs"]) == 5
    assert receipt["truncated"] is True
    assert sent_chunks[-1].endswith("[Truncated: digest exceeded max chunk count]")


def test_delivery_resume_skips_completed_duplicate_without_new_wrapper_sends(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, run_dir = _configure_delivery_runtime(monkeypatch, tmp_path, run_id="delivery-source-run")
    _write_digest(run_dir, fingerprint="fp-complete", chunks=["chunk-1", "chunk-2"])

    calls: list[tuple[str, str]] = []

    def fake_send_text_chunk(self: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        calls.append((target_id, chunk_text))
        return {"chat_id": "me", "message_id": str(100 + len(calls))}

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)

    first_payload, first_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="delivery-first-run",
        digest_ref="runs/delivery-source-run/digest.json",
        target_id="self",
    )

    assert first_exit_code is None
    assert first_payload["status"] == "ok"
    assert calls == [("self", "chunk-1"), ("self", "chunk-2")]

    second_payload, second_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="delivery-resume-run",
        digest_ref="runs/delivery-source-run/digest.json",
        target_id="self",
        resume="true",
    )

    assert second_exit_code is None
    receipt = json.loads((workspace / str(second_payload["payload_ref"])).read_text(encoding="utf-8"))
    assert receipt["delivery_status"] == "skipped_duplicate"
    assert receipt["sent_message_refs"] == []
    assert calls == [("self", "chunk-1"), ("self", "chunk-2")]


def test_delivery_same_run_duplicate_skip_preserves_existing_sent_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, run_dir = _configure_delivery_runtime(monkeypatch, tmp_path, run_id="same-run")
    _write_digest(run_dir, fingerprint="fp-same-run", chunks=["chunk-1", "chunk-2"])

    calls: list[tuple[str, str]] = []

    def fake_send_text_chunk(self: TelegramClientWrapper, *, target_id: str, chunk_text: str) -> dict[str, str]:
        calls.append((target_id, chunk_text))
        return {"chat_id": "me", "message_id": str(200 + len(calls))}

    monkeypatch.setattr(TelegramClientWrapper, "send_text_chunk", fake_send_text_chunk)

    first_payload, first_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="same-run",
        target_id="self",
    )

    assert first_exit_code is None
    first_receipt = json.loads((workspace / str(first_payload["payload_ref"])).read_text(encoding="utf-8"))
    assert first_receipt["delivery_status"] == "sent"
    assert first_receipt["sent_message_refs"] == [
        {"chat_id": "me", "message_id": "201"},
        {"chat_id": "me", "message_id": "202"},
    ]

    second_payload, second_exit_code = _invoke_delivery_cli(
        monkeypatch,
        capsys,
        run_id="same-run",
        target_id="self",
        resume="true",
    )

    assert second_exit_code is None
    second_receipt = json.loads((workspace / str(second_payload["payload_ref"])).read_text(encoding="utf-8"))
    assert second_receipt["delivery_status"] == "skipped_duplicate"
    assert second_receipt["sent_message_refs"] == [
        {"chat_id": "me", "message_id": "201"},
        {"chat_id": "me", "message_id": "202"},
    ]
    assert calls == [("self", "chunk-1"), ("self", "chunk-2")]
