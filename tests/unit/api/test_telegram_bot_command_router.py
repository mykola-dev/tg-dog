from unittest.mock import patch


def test_telegram_bot_command_subscribe_persists_subscription(stateless_api_client):
    with patch("api.routers.telegram_bot_commands.telegram_bot_command_runtime") as runtime:
        with patch("api.routers.telegram_bot_commands._load_webhook_path", return_value="workflow-1/bot%20command%20trigger/telegram-bot-command-trigger") as load_webhook_path:
            resp = stateless_api_client.post(
                "/telegram-bot-commands/subscribe",
                json={
                    "workflow_id": "workflow-1",
                    "node_id": "node-1",
                    "node_name": "Bot Command Trigger",
                    "webhook_mode": "production",
                    "command": "/run",
                    "require_private_chat": True,
                    "allow_connected_account_only": True,
                },
            )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["workflow_id"] == "workflow-1"
    assert payload["node_id"] == "node-1"
    assert payload["command"] == "/run"
    assert payload["webhook_url"] == "workflow-1/bot%20command%20trigger/telegram-bot-command-trigger"
    runtime.upsert_subscription.assert_called_once()
    runtime.refresh_webhooks.assert_called_once()
    load_webhook_path.assert_called_once_with(workflow_id="workflow-1", node_id="node-1", node_name="Bot Command Trigger")


def test_telegram_bot_command_subscribe_returns_server_error_on_runtime_failure(stateless_api_client):
    with patch("api.routers.telegram_bot_commands.telegram_bot_command_runtime") as runtime:
        runtime.upsert_subscription.side_effect = RuntimeError("db unavailable")
        with patch("api.routers.telegram_bot_commands._load_webhook_path", return_value="workflow-1/bot%20command%20trigger/telegram-bot-command-trigger"):
            resp = stateless_api_client.post(
                "/telegram-bot-commands/subscribe",
                json={
                    "workflow_id": "workflow-1",
                    "node_id": "node-1",
                    "node_name": "Bot Command Trigger",
                    "webhook_mode": "production",
                    "command": "/run",
                    "require_private_chat": True,
                    "allow_connected_account_only": True,
                },
            )

    assert resp.status_code == 500
    assert "db unavailable" in resp.json()["error"]


def test_telegram_bot_command_unsubscribe_removes_subscription(stateless_api_client):
    with patch("api.routers.telegram_bot_commands.telegram_bot_command_runtime") as runtime:
        resp = stateless_api_client.post(
            "/telegram-bot-commands/unsubscribe",
            json={
                "workflow_id": "workflow-1",
                "node_id": "node-1",
                "webhook_mode": "test",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    runtime.delete_subscription.assert_called_once_with(workflow_id="workflow-1", node_id="node-1", webhook_mode="test")
    runtime.refresh_webhooks.assert_called_once()


def test_telegram_bot_command_webhook_dispatches_update(stateless_api_client):
    with patch("api.routers.telegram_bot_commands.telegram_bot_command_runtime") as runtime:
        runtime.handle_update.return_value = {"matched": 1, "delivered": 1}
        resp = stateless_api_client.post(
            "/telegram-bot-commands/webhook",
            headers={"x-telegram-bot-api-secret-token": "secret-1"},
            json={"message": {"text": "/run"}},
        )

    assert resp.status_code == 200
    assert resp.json() == {"matched": 1, "delivered": 1}
    runtime.handle_update.assert_called_once_with({"message": {"text": "/run"}}, "secret-1")


def test_telegram_bot_command_config_returns_effective_url(stateless_api_client):
    with patch("api.routers.telegram_bot_commands.telegram_bot_command_runtime") as runtime:
        runtime.get_effective_webhook_base_url.return_value = "https://example.test"
        runtime.get_webhook_base_url_source.return_value = "database"
        runtime.get_ingress_mode.return_value = "webhook"
        runtime.is_override_active.return_value = True
        resp = stateless_api_client.get("/telegram-bot-commands/config")

    assert resp.status_code == 200
    assert resp.json() == {"webhook_base_url": "https://example.test", "source": "database", "ingress_mode": "webhook", "override_active": True}


def test_telegram_bot_command_config_updates_runtime_and_refreshes(stateless_api_client):
    with patch("api.routers.telegram_bot_commands.telegram_bot_command_runtime") as runtime:
        runtime.get_effective_webhook_base_url.return_value = "https://new.example.test"
        runtime.get_webhook_base_url_source.return_value = "database"
        runtime.get_ingress_mode.return_value = "webhook"
        runtime.is_override_active.return_value = True
        resp = stateless_api_client.post(
            "/telegram-bot-commands/config",
            json={"webhook_base_url": "https://new.example.test/", "ingress_mode": "webhook"},
        )

    assert resp.status_code == 200
    runtime.set_webhook_override.assert_called_once_with(webhook_base_url="https://new.example.test/", ingress_mode="webhook")
    runtime.refresh_webhooks.assert_called_once()
    assert resp.json() == {"webhook_base_url": "https://new.example.test", "source": "database", "ingress_mode": "webhook", "override_active": True}


def test_telegram_bot_command_config_can_clear_override_and_return_to_env(stateless_api_client):
    with patch("api.routers.telegram_bot_commands.telegram_bot_command_runtime") as runtime:
        runtime.get_effective_webhook_base_url.return_value = "https://env.example.test"
        runtime.get_webhook_base_url_source.return_value = "env"
        runtime.get_ingress_mode.return_value = "webhook"
        runtime.is_override_active.return_value = False

        resp = stateless_api_client.post(
            "/telegram-bot-commands/config",
            json={"use_env": True},
        )

    assert resp.status_code == 200
    runtime.clear_webhook_override.assert_called_once()
    runtime.refresh_webhooks.assert_called_once()
    assert resp.json() == {"webhook_base_url": "https://env.example.test", "source": "env", "ingress_mode": "webhook", "override_active": False}


def test_telegram_bot_command_reload_runtime(stateless_api_client):
    with patch("api.routers.telegram_bot_commands.telegram_bot_command_runtime") as runtime:
        runtime.get_effective_webhook_base_url.return_value = ""
        runtime.get_webhook_base_url_source.return_value = "unset"
        runtime.get_ingress_mode.return_value = "polling"
        runtime.is_override_active.return_value = False

        resp = stateless_api_client.post("/telegram-bot-commands/reload")

    assert resp.status_code == 200
    runtime.stop.assert_called_once()
    runtime.load_from_db.assert_called_once()
    runtime.refresh_webhooks.assert_called_once()
    assert resp.json() == {"webhook_base_url": "", "source": "unset", "ingress_mode": "polling", "override_active": False}
