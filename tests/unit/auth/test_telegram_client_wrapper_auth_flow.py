from __future__ import annotations

from pathlib import Path

import pytest

from services.shared.telegram.client import TelegramClientWrapper, _legacy_encrypt_secret


def test_start_login_persists_phone_code_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MASTER_KEY", "test_master_key")
    wrapper = TelegramClientWrapper(tmp_path)

    async def fake_send_code(*, api_id: str, api_hash: str, phone_number: str) -> str:
        return "phone-code-hash-123"

    monkeypatch.setattr(wrapper, "_async_send_code", fake_send_code, raising=False)

    response = wrapper.start_login(api_id="1", api_hash="hash", phone_number="+380000000000")

    flow = wrapper._load_json(wrapper.flow_file)
    assert flow["auth_flow_id"] == response["auth_flow_id"]
    assert flow["phone_code_hash"] == "phone-code-hash-123"


def test_submit_code_uses_persisted_phone_code_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MASTER_KEY", "test_master_key")
    wrapper = TelegramClientWrapper(tmp_path)

    async def fake_send_code(*, api_id: str, api_hash: str, phone_number: str) -> str:
        return "phone-code-hash-xyz"

    captured: dict[str, str] = {}

    async def fake_sign_in_with_code(
        *,
        api_id: str,
        api_hash: str,
        phone_number: str,
        login_code: str,
        phone_code_hash: str,
    ) -> dict[str, str | None]:
        captured["phone_code_hash"] = phone_code_hash
        captured["login_code"] = login_code
        return {"id": "1", "display_name": "Test User"}

    monkeypatch.setattr(wrapper, "_async_send_code", fake_send_code, raising=False)
    monkeypatch.setattr(wrapper, "_async_sign_in_with_code", fake_sign_in_with_code, raising=False)

    start = wrapper.start_login(api_id="1", api_hash="hash", phone_number="+380000000000")
    result = wrapper.submit_code(auth_flow_id=start["auth_flow_id"], login_code="77777")

    assert captured["phone_code_hash"] == "phone-code-hash-xyz"
    assert captured["login_code"] == "77777"
    assert result["account_state"] == "connected"


def test_submit_code_rejects_flow_without_phone_code_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MASTER_KEY", "test_master_key")
    wrapper = TelegramClientWrapper(tmp_path)

    async def fake_send_code(*, api_id: str, api_hash: str, phone_number: str) -> str:
        return "will-be-removed"

    monkeypatch.setattr(wrapper, "_async_send_code", fake_send_code, raising=False)

    start = wrapper.start_login(api_id="1", api_hash="hash", phone_number="+380000000000")
    flow = wrapper._load_json(wrapper.flow_file)
    flow.pop("phone_code_hash", None)
    wrapper._save_json(wrapper.flow_file, flow)

    with pytest.raises(TimeoutError, match="AUTH_FLOW_EXPIRED"):
        wrapper.submit_code(auth_flow_id=start["auth_flow_id"], login_code="77777")


def test_status_does_not_downgrade_connected_state_inside_running_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    wrapper._persist_auth_state(
        account_state="connected",
        api_id="1",
        api_hash_encrypted=_legacy_encrypt_secret("hash"),
        last_successful_auth_at="2026-01-01T00:00:00+00:00",
        account_profile={"id": "1", "display_name": "Test User"},
    )
    monkeypatch.setattr(wrapper, "_has_running_event_loop", lambda: True)

    result = wrapper.status()

    assert result["account_state"] == "connected"
    persisted = wrapper._load_json(wrapper.state_file)
    assert persisted["account_state"] == "connected"
    assert persisted["last_auth_error"] is None


def test_status_recovers_from_false_reauth_required_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    wrapper._persist_auth_state(
        account_state="reauth_required",
        api_id="1",
        api_hash_encrypted=_legacy_encrypt_secret("hash"),
        last_successful_auth_at="2026-01-01T00:00:00+00:00",
        last_auth_error={"code": "STATUS_CHECK_FAILED", "message": "asyncio.run() cannot be called from a running event loop"},
        account_profile={"id": "1", "display_name": "Stale User"},
    )

    async def fake_async_status(*, api_id: str, api_hash: str) -> dict[str, str]:
        assert api_id == "1"
        assert api_hash == "hash"
        return {"id": "1", "display_name": "Recovered User"}

    monkeypatch.setattr(wrapper, "_async_status", fake_async_status, raising=False)

    result = wrapper.status()

    assert result["account_state"] == "connected"
    assert result["account_profile"] == {"id": "1", "display_name": "Recovered User"}
    assert result["last_auth_error"] is None
    persisted = wrapper._load_json(wrapper.state_file)
    assert persisted["account_state"] == "connected"
    assert persisted["account_profile"] == {"id": "1", "display_name": "Recovered User"}
    assert persisted["last_auth_error"] is None
