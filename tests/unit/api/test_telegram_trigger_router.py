from unittest.mock import MagicMock, patch


def test_telegram_trigger_subscribe_persists_subscription(stateless_api_client):
    with patch("api.routers.telegram_trigger.telegram_trigger_runtime") as runtime:
        resp = stateless_api_client.post(
            "/telegram-trigger/subscribe",
            json={
                "workflow_id": "workflow-1",
                "node_id": "node-1",
                "webhook_mode": "production",
                "dialog_id": "12345",
                "dialog_name": "Alice",
                "webhook_url": "http://n8n/webhook/test",
                "only_incoming": True,
                "ignore_self": True,
                "ignore_service_messages": True,
                "include_media": True,
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["workflow_id"] == "workflow-1"
    assert payload["node_id"] == "node-1"
    assert payload["webhook_mode"] == "production"
    assert payload["dialog_id"] == "12345"
    runtime.upsert_subscription.assert_called_once()


def test_telegram_trigger_subscribe_returns_server_error_on_runtime_failure(stateless_api_client):
    with patch("api.routers.telegram_trigger.telegram_trigger_runtime") as runtime:
        runtime.upsert_subscription.side_effect = RuntimeError("db unavailable")
        resp = stateless_api_client.post(
            "/telegram-trigger/subscribe",
            json={
                "workflow_id": "workflow-1",
                "node_id": "node-1",
                "webhook_mode": "production",
                "dialog_id": "12345",
                "dialog_name": "Alice",
                "webhook_url": "http://n8n/webhook/test",
                "only_incoming": True,
                "ignore_self": True,
                "ignore_service_messages": True,
                "include_media": True,
            },
        )

    assert resp.status_code == 500
    assert "db unavailable" in resp.json()["error"]


def test_telegram_trigger_unsubscribe_removes_subscription(stateless_api_client):
    with patch("api.routers.telegram_trigger.telegram_trigger_runtime") as runtime:
        resp = stateless_api_client.post(
            "/telegram-trigger/unsubscribe",
            json={
                "workflow_id": "workflow-1",
                "node_id": "node-1",
                "webhook_mode": "test",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    runtime.delete_subscription.assert_called_once_with(workflow_id="workflow-1", node_id="node-1", webhook_mode="test")
