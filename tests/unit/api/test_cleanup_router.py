from unittest.mock import patch


def test_cleanup_router_returns_combined_payload(stateless_api_client):
    response_payload = {
        "mode": "combined",
        "output_format": "markdown",
        "message_count": 1,
        "combined_text": "## Example\n\nHello",
        "formatted_messages": [
            {"source_id": "-100123", "message_id": "1", "formatted_text": "## Example\n\nHello"}
        ],
    }

    with patch("api.routers.cleanup.format_messages", return_value=response_payload):
        resp = stateless_api_client.post(
            "/messages/cleanup",
            json={
                "messages": [
                    {
                        "schema_version": "v1",
                        "source_kind": "channel",
                        "source_id": "-100123",
                        "source_title": "Example",
                        "message_id": "1",
                        "message_timestamp": "2026-03-25T12:00:00Z",
                        "author_id": None,
                        "author_title": None,
                        "text": "Hello",
                        "reply_to_message_id": None,
                        "forwarded_from_source_id": None,
                        "is_outbound": False,
                        "is_from_self": False,
                        "is_service_message": False,
                        "media_items": [],
                        "ingestion_meta": {},
                    }
                ]
            },
        )

    assert resp.status_code == 200
    assert resp.json()["combined_text"] == "## Example\n\nHello"
