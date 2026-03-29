"use strict";

Object.defineProperty(exports, "__esModule", { value: true });
exports.TelegramBotCommandTrigger = void 0;

const { NodeConnectionTypes } = require("n8n-workflow");

const API_BASE_URL = process.env.TELEGRAM_SOURCE_SELECTOR_API_URL || "http://api:8000";
const INTERNAL_WEBHOOK_BASE_URL = process.env.N8N_INTERNAL_WEBHOOK_BASE_URL || "http://n8n:5678";
function logToUi(context, ...messages) {
    if (typeof context.sendMessageToUI !== "function") {
        return;
    }
    try {
        context.sendMessageToUI(...messages);
    } catch (_error) {
    }
}

async function subscribeCommandTrigger(payload) {
    const response = await fetch(`${API_BASE_URL}/telegram-bot-commands/subscribe`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Telegram bot command subscribe failed with status ${response.status}: ${body}`);
    }
    return body ? JSON.parse(body) : {};
}

function normalizeWebhookUrl(rawWebhookUrl) {
    if (!rawWebhookUrl) {
        return rawWebhookUrl;
    }

    try {
        const webhookUrl = new URL(String(rawWebhookUrl));
        const internalBaseUrl = new URL(INTERNAL_WEBHOOK_BASE_URL);
        webhookUrl.protocol = internalBaseUrl.protocol;
        webhookUrl.hostname = internalBaseUrl.hostname;
        webhookUrl.port = internalBaseUrl.port;
        return webhookUrl.toString();
    } catch (_error) {
        return rawWebhookUrl;
    }
}

async function unsubscribeCommandTrigger(payload) {
    const response = await fetch(`${API_BASE_URL}/telegram-bot-commands/unsubscribe`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Telegram bot command unsubscribe failed with status ${response.status}: ${body}`);
    }
    return body ? JSON.parse(body) : {};
}

function getWorkflowIdentity(context) {
    const workflow = context.getWorkflow();
    const node = context.getNode();
    return {
        workflowId: String((workflow && workflow.id) || ""),
        nodeId: String((node && (node.id || node.name)) || "telegram-bot-command-trigger"),
        nodeName: String((node && node.name) || "TG Dog Bot Command Trigger"),
    };
}

function getWebhookModeFromUrl(webhookUrl) {
    return String(webhookUrl || "").includes("/webhook-test/") ? "test" : "production";
}

async function buildSubscriptionPayload(context) {
    const webhookUrl = normalizeWebhookUrl(context.getNodeWebhookUrl("default"));
    const webhookMode = getWebhookModeFromUrl(webhookUrl);
    const command = String(context.getNodeParameter("command")).trim();
    const requirePrivateChat = Boolean(context.getNodeParameter("requirePrivateChat"));
    const allowConnectedAccountOnly = Boolean(context.getNodeParameter("allowConnectedAccountOnly"));
    const { workflowId, nodeId, nodeName } = getWorkflowIdentity(context);

    return {
        workflow_id: workflowId,
        node_id: nodeId,
        node_name: nodeName,
        webhook_mode: webhookMode,
        command,
        require_private_chat: requirePrivateChat,
        allow_connected_account_only: allowConnectedAccountOnly,
    };
}

class TelegramBotCommandTrigger {
    constructor() {
        this.description = {
            displayName: "TG Dog Bot Command Trigger",
            name: "telegramBotCommandTrigger",
            icon: "fa:telegram",
            group: ["trigger"],
            version: 1,
            description: "Start a workflow when the Telegram bot receives a command",
            defaults: {
                name: "TG Dog Bot Command Trigger",
                color: "#229ED9",
            },
            triggerPanel: {
                header: "",
                executionsHelp: {
                    inactive: "Execute the step, then send the configured bot command to test the trigger.",
                    active: "This workflow will execute automatically when the configured bot command is received.",
                },
                activationHint: "Publish the workflow to keep the bot command trigger active continuously.",
            },
            inputs: [],
            outputs: [NodeConnectionTypes.Main],
            webhooks: [
                {
                    name: "default",
                    httpMethod: "POST",
                    responseMode: "onReceived",
                    path: "telegram-bot-command-trigger",
                },
            ],
            properties: [
                {
                    displayName: "Command",
                    name: "command",
                    type: "string",
                    default: "/run",
                    required: true,
                    noDataExpression: true,
                    description: "Bot command that should trigger this workflow",
                },
                {
                    displayName: "Only Connected Account",
                    name: "allowConnectedAccountOnly",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                    description: "Only allow commands from the currently connected Telegram account",
                },
                {
                    displayName: "Require Private Chat",
                    name: "requirePrivateChat",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                    description: "Ignore commands sent outside one-on-one private chats",
                },
            ],
        };
        this.webhookMethods = {
            default: {
                async checkExists() {
                    return false;
                },
                async create() {
                    const staticData = this.getWorkflowStaticData("node");
                    const payload = await buildSubscriptionPayload(this);
                    const subscription = await subscribeCommandTrigger(payload);
                    staticData.subscriptionId = subscription.subscription_id;
                    staticData.workflowId = payload.workflow_id;
                    staticData.nodeId = payload.node_id;
                    staticData.webhookMode = payload.webhook_mode;
                    return true;
                },
                async delete() {
                    const staticData = this.getWorkflowStaticData("node");
                    const { workflowId, nodeId } = getWorkflowIdentity(this);
                    const unsubscribePayload = {
                        workflow_id: String(staticData.workflowId || workflowId || ""),
                        node_id: String(staticData.nodeId || nodeId || ""),
                        webhook_mode: String(staticData.webhookMode || "production"),
                    };
                    if (!unsubscribePayload.workflow_id || !unsubscribePayload.node_id) {
                        return false;
                    }
                    await unsubscribeCommandTrigger(unsubscribePayload);
                    delete staticData.subscriptionId;
                    delete staticData.workflowId;
                    delete staticData.nodeId;
                    delete staticData.webhookMode;
                    return true;
                },
            },
        };
    }

    async webhook() {
        const body = this.getBodyData();
        logToUi(this, "Telegram bot command trigger received update", {
            command: body && body.command,
            chat_id: body && body.chat_id,
            user_id: body && body.user_id,
            message_id: body && body.message_id,
        });
        return {
            workflowData: [this.helpers.returnJsonArray([body])],
        };
    }
}

exports.TelegramBotCommandTrigger = TelegramBotCommandTrigger;
