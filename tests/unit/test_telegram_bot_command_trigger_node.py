from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_bot_command_trigger_uses_internal_webhook_base_url() -> None:
    source = (ROOT / "n8n/custom-nodes/telegram-bot-command-trigger/TelegramBotCommandTrigger.node.js").read_text(
        encoding="utf-8"
    )

    assert 'const INTERNAL_WEBHOOK_BASE_URL = process.env.N8N_INTERNAL_WEBHOOK_BASE_URL || "http://n8n:5678";' in source
    assert 'webhookUrl.protocol = internalBaseUrl.protocol;' in source
    assert 'webhookUrl.hostname = internalBaseUrl.hostname;' in source
    assert 'webhookUrl.port = internalBaseUrl.port;' in source


def test_bot_command_trigger_publishes_current_subscription_contract() -> None:
    source = (ROOT / "n8n/custom-nodes/telegram-bot-command-trigger/TelegramBotCommandTrigger.node.js").read_text(
        encoding="utf-8"
    )

    assert 'workflow_id: workflowId,' in source
    assert 'node_id: nodeId,' in source
    assert 'node_name: nodeName,' in source
    assert 'command,' in source
    assert 'require_private_chat: requirePrivateChat,' in source
    assert 'allow_connected_account_only: allowConnectedAccountOnly,' in source


def test_bot_command_trigger_exposes_only_current_guard_fields() -> None:
    source = (ROOT / "n8n/custom-nodes/telegram-bot-command-trigger/TelegramBotCommandTrigger.node.js").read_text(
        encoding="utf-8"
    )

    assert 'displayName: "Command"' in source
    assert 'displayName: "Only Connected Account"' in source
    assert 'displayName: "Require Private Chat"' in source
    assert "allowedUserIds" not in source
    assert "allowedChatIds" not in source
    assert "BOT_TRIGGER_ALLOWED_CHAT_IDS" not in source
