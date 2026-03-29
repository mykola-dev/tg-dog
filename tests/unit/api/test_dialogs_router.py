from unittest.mock import patch, MagicMock
from services.shared.telegram.errors import TelegramAuthError


def test_get_dialogs_returns_list(stateless_api_client):
    mock_dialogs = [
        {"id": "-100123", "name": "Tech News", "kind": "channel", "username": "technews",
         "last_message_date": "2026-03-20T12:00:00+00:00"},
        {"id": "-100456", "name": "My Group", "kind": "group", "username": "",
         "last_message_date": None},
    ]
    with patch("api.routers.dialogs.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.list_dialogs.return_value = mock_dialogs
        MockWrapper.return_value = instance
        resp = stateless_api_client.get("/dialogs")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "Tech News"
    assert data[0]["kind"] == "channel"


def test_get_dialogs_returns_503_when_not_connected(stateless_api_client):
    with patch("api.routers.dialogs.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.list_dialogs.side_effect = TelegramAuthError(code="NOT_CONNECTED")
        MockWrapper.return_value = instance
        resp = stateless_api_client.get("/dialogs")

    assert resp.status_code == 503
    assert "not connected" in resp.json()["error"].lower()
