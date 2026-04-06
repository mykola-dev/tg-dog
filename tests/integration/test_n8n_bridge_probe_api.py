from datetime import datetime

from fastapi.testclient import TestClient

from api.main import create_app


def test_n8n_bridge_probe_returns_explicit_contract() -> None:
    client = TestClient(create_app(), raise_server_exceptions=True)
    response = client.get("/n8n/bridge-probe")

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"ok", "bridge", "service", "timestamp"}
    assert data["ok"] is True
    assert data["bridge"] == "n8n"
    assert data["service"] == "tg-dog-api"
    assert isinstance(data["timestamp"], str)
    assert datetime.fromisoformat(data["timestamp"])
