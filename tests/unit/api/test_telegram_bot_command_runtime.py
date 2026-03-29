from __future__ import annotations

import threading

from api.telegram_bot_command_runtime import BotCommandSubscription, TelegramBotCommandRuntime


def _subscription(**overrides) -> BotCommandSubscription:
    payload = {
        "id": "sub-1",
        "workflow_id": "workflow-1",
        "node_id": "node-1",
        "webhook_mode": "production",
        "command": "/run",
        "require_private_chat": True,
        "allow_connected_account_only": True,
        "webhook_path": "workflow-1/node-1/telegram-bot-command-trigger",
    }
    payload.update(overrides)
    return BotCommandSubscription(**payload)


def test_handle_update_matches_command_and_delivers(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    subscription = _subscription(node_id="telegram-bot-command-trigger")
    runtime._subscriptions = {subscription.id: subscription}
    monkeypatch.setattr("api.telegram_bot_command_runtime.load_config", lambda: type("Config", (), {"telegram_bot_token": "test-token"})())
    monkeypatch.setattr(runtime, "_connected_account_user_id", lambda: "321")

    calls = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return _FakeResponse()

    monkeypatch.setattr("api.telegram_bot_command_runtime.httpx.post", fake_post)

    result = runtime.handle_update(
        {
            "message": {
                "text": "/run extra words",
                "message_id": 10,
                "date": 1774779000,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 321, "first_name": "Mykola"},
            }
        },
        runtime._webhook_secret("test-token"),
    )

    assert result == {"matched": 1, "delivered": 1}
    assert len(calls) == 1
    assert calls[0][0] == "http://n8n:5678/webhook/workflow-1/node-1/telegram-bot-command-trigger"
    assert calls[0][1]["command"] == "/run"
    assert calls[0][1]["chat_id"] == "123"


def test_handle_update_respects_require_private_chat(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    subscription = _subscription(node_id="telegram-bot-command-trigger", require_private_chat=True)
    runtime._subscriptions = {subscription.id: subscription}
    monkeypatch.setattr("api.telegram_bot_command_runtime.httpx.post", lambda *args, **kwargs: None)
    monkeypatch.setattr("api.telegram_bot_command_runtime.load_config", lambda: type("Config", (), {"telegram_bot_token": "test-token"})())
    monkeypatch.setattr(runtime, "_connected_account_user_id", lambda: "111")

    result = runtime.handle_update(
        {
            "message": {
                "text": "/run",
                "message_id": 10,
                "date": 1774779000,
                "chat": {"id": -100123, "type": "group"},
                "from": {"id": 111, "first_name": "Mykola"},
            }
        },
        runtime._webhook_secret("test-token"),
    )

    assert result == {"matched": 0, "delivered": 0}


def test_handle_update_ignores_wrong_secret(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    subscription = _subscription(node_id="telegram-bot-command-trigger")
    runtime._subscriptions = {subscription.id: subscription}
    monkeypatch.setattr("api.telegram_bot_command_runtime.httpx.post", lambda *args, **kwargs: None)
    monkeypatch.setattr("api.telegram_bot_command_runtime.load_config", lambda: type("Config", (), {"telegram_bot_token": "test-token"})())

    result = runtime.handle_update(
        {
            "message": {
                "text": "/run",
                "message_id": 10,
                "date": 1774779000,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 321, "first_name": "Mykola"},
            }
        },
        "wrong-secret",
    )

    assert result == {"matched": 0, "delivered": 0}


def test_handle_update_allows_only_connected_account_by_default(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    subscription = _subscription(node_id="telegram-bot-command-trigger")
    runtime._subscriptions = {subscription.id: subscription}
    monkeypatch.setattr("api.telegram_bot_command_runtime.httpx.post", lambda *args, **kwargs: None)
    monkeypatch.setattr("api.telegram_bot_command_runtime.load_config", lambda: type("Config", (), {"telegram_bot_token": "test-token"})())
    monkeypatch.setattr(runtime, "_connected_account_user_id", lambda: "658293575")

    result = runtime.handle_update(
        {
            "message": {
                "text": "/run",
                "message_id": 10,
                "date": 1774779000,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 111, "first_name": "NotMykola"},
            }
        },
        runtime._webhook_secret("test-token"),
    )

    assert result == {"matched": 0, "delivered": 0}


def test_webhook_secret_is_stable_hash():
    runtime = TelegramBotCommandRuntime()
    assert runtime._webhook_secret("abc:123") == runtime._webhook_secret("abc:123")
    assert runtime._webhook_secret("abc:123") != runtime._webhook_secret("zzz:999")


def test_internal_webhook_url_preserves_encoded_node_name():
    runtime = TelegramBotCommandRuntime()
    subscription = _subscription(webhook_path="workflow-1/bot%20command%20trigger/telegram-bot-command-trigger")

    assert (
        runtime._internal_webhook_url(subscription)
        == "http://n8n:5678/webhook/workflow-1/bot%2520command%2520trigger/telegram-bot-command-trigger"
    )


def test_effective_webhook_base_url_prefers_database_override(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    runtime._override_enabled = True
    runtime._webhook_base_url_override = "https://db.example.test"
    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.load_config",
        lambda: type("Config", (), {"telegram_bot_webhook_base_url": "https://env.example.test"})(),
    )

    assert runtime.get_effective_webhook_base_url() == "https://db.example.test"
    assert runtime.get_webhook_base_url_source() == "database"
    assert runtime.get_ingress_mode() == "webhook"


def test_effective_webhook_base_url_falls_back_to_env(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.load_config",
        lambda: type("Config", (), {"telegram_bot_webhook_base_url": "https://env.example.test/"})(),
    )

    assert runtime.get_effective_webhook_base_url() == "https://env.example.test"
    assert runtime.get_webhook_base_url_source() == "env"
    assert runtime.get_ingress_mode() == "webhook"


def test_effective_webhook_base_url_respects_polling_override(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    runtime._override_enabled = True
    runtime._webhook_mode_override = "polling"
    runtime._webhook_base_url_override = None

    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.load_config",
        lambda: type("Config", (), {"telegram_bot_webhook_base_url": "https://env.example.test/"})(),
    )

    assert runtime.get_effective_webhook_base_url() == ""
    assert runtime.get_webhook_base_url_source() == "database"
    assert runtime.get_ingress_mode() == "polling"


def test_refresh_webhooks_uses_polling_when_public_base_url_missing(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    runtime._subscriptions = {"sub-1": _subscription()}

    delete_calls = []
    poll_calls = []

    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.load_config",
        lambda: type("Config", (), {"telegram_bot_token": "123:token", "telegram_bot_webhook_base_url": ""})(),
    )
    monkeypatch.setattr(runtime, "_delete_webhook", lambda token, drop_pending_updates=False: delete_calls.append((token, drop_pending_updates)))
    monkeypatch.setattr(runtime, "_start_polling", lambda token: poll_calls.append(token))

    runtime.refresh_webhooks()

    assert delete_calls == [("123:token", False)]
    assert poll_calls == ["123:token"]


def test_refresh_webhooks_uses_polling_when_mode_override_requests_it(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    runtime._subscriptions = {"sub-1": _subscription()}
    runtime._override_enabled = True
    runtime._webhook_mode_override = "polling"

    delete_calls = []
    poll_calls = []

    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.load_config",
        lambda: type("Config", (), {"telegram_bot_token": "123:token", "telegram_bot_webhook_base_url": "https://env.example.test"})(),
    )
    monkeypatch.setattr(runtime, "_delete_webhook", lambda token, drop_pending_updates=False: delete_calls.append((token, drop_pending_updates)))
    monkeypatch.setattr(runtime, "_start_polling", lambda token: poll_calls.append(token))

    runtime.refresh_webhooks()

    assert delete_calls == [("123:token", False)]
    assert poll_calls == ["123:token"]


def test_refresh_webhooks_uses_webhook_when_public_base_url_present(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    runtime._subscriptions = {"sub-1": _subscription()}

    stop_calls = []
    request_calls = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.load_config",
        lambda: type("Config", (), {"telegram_bot_token": "123:token", "telegram_bot_webhook_base_url": "https://bot.example.test"})(),
    )
    monkeypatch.setattr(runtime, "_stop_polling", lambda: stop_calls.append(True))
    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.httpx.post",
        lambda url, json, timeout: request_calls.append((url, json, timeout)) or _FakeResponse(),
    )

    runtime.refresh_webhooks()

    assert stop_calls == [True]
    assert request_calls[0][0] == "https://api.telegram.org/bot123:token/setWebhook"
    assert request_calls[0][1]["url"] == "https://bot.example.test/telegram-bot-commands/webhook"


def test_runtime_uses_env_when_no_override_is_active(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    runtime._override_enabled = False
    runtime._webhook_base_url_override = "https://db.example.test"
    runtime._webhook_mode_override = "polling"

    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.load_config",
        lambda: type("Config", (), {"telegram_bot_webhook_base_url": "https://env.example.test"})(),
    )

    assert runtime.get_effective_webhook_base_url() == "https://env.example.test"
    assert runtime.get_webhook_base_url_source() == "env"
    assert runtime.get_ingress_mode() == "webhook"
    assert runtime.is_override_active() is False


def test_set_webhook_override_enables_database_override(monkeypatch):
    runtime = TelegramBotCommandRuntime()

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("api.telegram_bot_command_runtime.get_session_factory", lambda: lambda: _FakeDb())

    runtime.set_webhook_override(webhook_base_url="https://bot.example.test/", ingress_mode="webhook")

    assert runtime.is_override_active() is True
    assert runtime.get_ingress_mode() == "webhook"
    assert runtime.get_effective_webhook_base_url() == "https://bot.example.test"


def test_clear_webhook_override_restores_env_control(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    runtime._override_enabled = True
    runtime._webhook_base_url_override = None
    runtime._webhook_mode_override = "polling"

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("api.telegram_bot_command_runtime.get_session_factory", lambda: lambda: _FakeDb())
    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.load_config",
        lambda: type("Config", (), {"telegram_bot_webhook_base_url": "https://env.example.test"})(),
    )

    runtime.clear_webhook_override()

    assert runtime.is_override_active() is False
    assert runtime.get_ingress_mode() == "webhook"
    assert runtime.get_effective_webhook_base_url() == "https://env.example.test"


def test_refresh_webhooks_deletes_webhook_and_stops_polling_without_subscriptions(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    runtime._subscriptions = {}

    delete_calls = []
    stop_calls = []

    monkeypatch.setattr(
        "api.telegram_bot_command_runtime.load_config",
        lambda: type("Config", (), {"telegram_bot_token": "123:token", "telegram_bot_webhook_base_url": "https://bot.example.test"})(),
    )
    monkeypatch.setattr(runtime, "_delete_webhook", lambda token, drop_pending_updates=False: delete_calls.append((token, drop_pending_updates)))
    monkeypatch.setattr(runtime, "_stop_polling", lambda: stop_calls.append(True))

    runtime.refresh_webhooks()

    assert stop_calls == [True]
    assert delete_calls == [("123:token", False)]


def test_start_polling_does_not_spawn_duplicate_thread_for_same_token(monkeypatch):
    runtime = TelegramBotCommandRuntime()

    class _AliveThread:
        def is_alive(self):
            return True

    runtime._poll_thread = _AliveThread()
    runtime._poll_token = "123:token"
    runtime._poll_stop_event = threading.Event()

    runtime._start_polling("123:token")

    assert runtime._poll_restart_token is None
    assert runtime._poll_stop_event.is_set() is False


def test_start_polling_requests_restart_when_token_changes(monkeypatch):
    runtime = TelegramBotCommandRuntime()

    class _AliveThread:
        def is_alive(self):
            return True

    runtime._poll_thread = _AliveThread()
    runtime._poll_token = "old-token"
    runtime._poll_stop_event = threading.Event()

    runtime._start_polling("new-token")

    assert runtime._poll_restart_token == "new-token"
    assert runtime._poll_stop_event.is_set() is True


def test_finish_poll_thread_restarts_with_requested_token(monkeypatch):
    runtime = TelegramBotCommandRuntime()
    restart_calls = []

    runtime._poll_thread = threading.current_thread()
    runtime._poll_token = "old-token"
    runtime._poll_restart_token = "new-token"

    monkeypatch.setattr(runtime, "_start_polling", lambda token: restart_calls.append(token))

    restart_token = runtime._finish_poll_thread(threading.current_thread())
    if restart_token:
        runtime._start_polling(restart_token)

    assert restart_calls == ["new-token"]
    assert runtime._poll_thread is None
    assert runtime._poll_token is None
    assert runtime._poll_restart_token is None
