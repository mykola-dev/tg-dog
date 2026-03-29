from unittest.mock import MagicMock, patch


def test_send_targets_router_includes_saved_messages_and_sendable_dialogs(stateless_api_client):
    dialogs = [
        {
            "id": "-100123",
            "name": "Writable Channel",
            "kind": "channel",
            "username": "writable",
            "last_message_date": None,
            "can_send": True,
        },
        {
            "id": "-100999",
            "name": "Read Only Channel",
            "kind": "channel",
            "username": "readonly",
            "last_message_date": None,
            "can_send": False,
        },
    ]
    with patch("api.routers.dialogs.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.list_dialogs.return_value = dialogs
        MockWrapper.return_value = instance
        resp = stateless_api_client.get("/dialogs/send-targets")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload[0]["id"] == "self"
    assert payload[0]["can_send"] is True
    assert any(item["id"] == "-100123" for item in payload)
    assert not any(item["id"] == "-100999" for item in payload)


def test_send_targets_router_hides_saved_messages_for_bot_mode(stateless_api_client):
    dialogs = [
        {
            "id": "-100123",
            "name": "Writable Channel",
            "kind": "channel",
            "username": "writable",
            "last_message_date": None,
            "can_send": True,
        }
    ]
    with patch("api.routers.dialogs.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.list_dialogs.return_value = dialogs
        MockWrapper.return_value = instance
        resp = stateless_api_client.get("/dialogs/send-targets?sender_mode=bot")

    assert resp.status_code == 200
    payload = resp.json()
    assert not any(item["id"] == "self" for item in payload)
    assert payload[0]["id"] == "-100123"
