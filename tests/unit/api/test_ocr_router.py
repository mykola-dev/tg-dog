from pathlib import Path
from unittest.mock import patch


def test_ocr_router_enriches_example_image(stateless_api_client):
    image_path = str((Path(__file__).resolve().parents[3] / "example.jpg").resolve())

    enriched_messages = [
        {
            "schema_version": "v1",
            "source_kind": "channel",
            "source_id": "-100123",
            "source_title": "Example",
            "message_id": "1",
            "message_timestamp": "2026-03-25T12:00:00+00:00",
            "author_id": None,
            "author_title": None,
            "text": "",
            "reply_to_message_id": None,
            "forwarded_from_source_id": None,
            "is_outbound": False,
            "is_from_self": False,
            "is_service_message": False,
            "media_items": [
                {
                    "media_kind": "image",
                    "file_ref": image_path,
                    "ocr_status": "done",
                    "ocr_text": "text from example.jpg",
                    "ocr_confidence_hint": 0.75,
                    "ocr_error_code": None,
                    "ocr_error_message": None,
                }
            ],
            "ocr_text": "text from example.jpg",
            "ingestion_meta": {},
        }
    ]

    with patch("api.routers.ocr.enrich_messages_with_ocr", return_value=(enriched_messages, {"items_processed": 1, "failures": 0})):
        resp = stateless_api_client.post(
            "/ocr/messages",
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
                        "text": "",
                        "reply_to_message_id": None,
                        "forwarded_from_source_id": None,
                        "is_outbound": False,
                        "is_from_self": False,
                        "is_service_message": False,
                        "media_items": [
                            {
                                "media_kind": "image",
                                "file_ref": image_path,
                                "ocr_status": "pending",
                            }
                        ],
                        "ingestion_meta": {},
                    }
                ],
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["media_items"][0]["ocr_status"] == "done"
    assert payload[0]["media_items"][0]["ocr_text"] == "text from example.jpg"
    assert payload[0]["ocr_text"] == "text from example.jpg"
