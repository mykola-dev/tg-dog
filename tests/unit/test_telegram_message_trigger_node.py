from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_message_trigger_always_uses_internal_webhook_base_url() -> None:
    source = (ROOT / "n8n/custom-nodes/telegram-message-trigger/TelegramMessageTrigger.node.js").read_text(
        encoding="utf-8"
    )

    assert 'const INTERNAL_WEBHOOK_BASE_URL = process.env.N8N_INTERNAL_WEBHOOK_BASE_URL || "http://n8n:5678";' in source
    assert 'webhookUrl.protocol = internalBaseUrl.protocol;' in source
    assert 'webhookUrl.hostname = internalBaseUrl.hostname;' in source
    assert 'webhookUrl.port = internalBaseUrl.port;' in source
    assert 'hostname !== "localhost" && hostname !== "127.0.0.1"' not in source
