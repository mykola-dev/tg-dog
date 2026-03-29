"use strict";

Object.defineProperty(exports, "__esModule", { value: true });
exports.TelegramMessageTrigger = void 0;

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

async function fetchDialogs() {
    const response = await fetch(`${API_BASE_URL}/dialogs`, {
        headers: { Accept: "application/json" },
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Telegram dialog fetch failed with status ${response.status}: ${body}`);
    }
    const payload = body ? JSON.parse(body) : [];
    if (!Array.isArray(payload)) {
        throw new Error(`Telegram dialog response must be an array, got ${typeof payload}`);
    }
    return payload;
}

async function subscribeTrigger(payload) {
    const response = await fetch(`${API_BASE_URL}/telegram-trigger/subscribe`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Telegram trigger subscribe failed with status ${response.status}: ${body}`);
    }
    return body ? JSON.parse(body) : {};
}

async function unsubscribeTrigger(payload) {
    const response = await fetch(`${API_BASE_URL}/telegram-trigger/unsubscribe`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Telegram trigger unsubscribe failed with status ${response.status}: ${body}`);
    }
    return body ? JSON.parse(body) : {};
}

function getWorkflowIdentity(context) {
    const workflow = context.getWorkflow();
    const node = context.getNode();
    return {
        workflowId: String((workflow && workflow.id) || ""),
        nodeId: String((node && (node.id || node.name)) || "telegram-message-trigger"),
    };
}

function getWebhookModeFromUrl(webhookUrl) {
    return String(webhookUrl || "").includes("/webhook-test/") ? "test" : "production";
}

async function buildSubscriptionPayload(context) {
    const webhookUrl = normalizeWebhookUrl(context.getNodeWebhookUrl("default"));
    const webhookMode = getWebhookModeFromUrl(webhookUrl);
    const dialogId = String(context.getNodeParameter("dialogId"));
    const onlyIncoming = Boolean(context.getNodeParameter("onlyIncoming"));
    const ignoreSelf = Boolean(context.getNodeParameter("ignoreSelf"));
    const ignoreServiceMessages = Boolean(context.getNodeParameter("ignoreServiceMessages"));
    const includeMedia = Boolean(context.getNodeParameter("includeMedia"));
    const { workflowId, nodeId } = getWorkflowIdentity(context);

    return {
        workflow_id: workflowId,
        node_id: nodeId,
        webhook_mode: webhookMode,
        dialog_id: dialogId,
        dialog_name: "",
        webhook_url: webhookUrl,
        only_incoming: onlyIncoming,
        ignore_self: ignoreSelf,
        ignore_service_messages: ignoreServiceMessages,
        include_media: includeMedia,
    };
}

class TelegramMessageTrigger {
    constructor() {
        this.description = {
            displayName: "TG Dog Message Trigger",
            name: "telegramMessageTrigger",
            icon: "fa:telegram",
            group: ["trigger"],
            version: 1,
            description: "Start a workflow when a new Telegram user-account message arrives",
            defaults: {
                name: "TG Dog Message Trigger",
                color: "#229ED9",
            },
            triggerPanel: {
                header: "",
                executionsHelp: {
                    inactive: "Execute the step, then send a new message to the selected Telegram dialog to trigger a test execution.",
                    active: "This workflow will execute automatically for new messages in the selected Telegram dialog.",
                },
                activationHint: "Publish the workflow to keep the Telegram listener active continuously.",
            },
            inputs: [],
            outputs: [NodeConnectionTypes.Main],
            webhooks: [
                {
                    name: "default",
                    httpMethod: "POST",
                    responseMode: "onReceived",
                    path: "telegram-message-trigger",
                },
            ],
            properties: [
                {
                    displayName: "Dialog",
                    name: "dialogId",
                    type: "options",
                    default: "",
                    required: true,
                    noDataExpression: true,
                    typeOptions: {
                        loadOptionsMethod: "getSelectableDialogs",
                    },
                    description: "Listen for new messages in this Telegram dialog",
                },
                {
                    displayName: "Only Incoming",
                    name: "onlyIncoming",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                },
                {
                    displayName: "Ignore Self",
                    name: "ignoreSelf",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                },
                {
                    displayName: "Ignore Service Messages",
                    name: "ignoreServiceMessages",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                },
                {
                    displayName: "Include Media",
                    name: "includeMedia",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                    description: "Download supported image media so downstream OCR can process it",
                },
            ],
        };
        this.methods = {
            loadOptions: {
                async getSelectableDialogs() {
                    const dialogs = await fetchDialogs();
                    return dialogs.map((dialog) => ({
                        name: `${dialog.name} (${dialog.kind})`,
                        value: String(dialog.id),
                    }));
                },
            },
        };
        this.webhookMethods = {
            default: {
                async checkExists() {
                    return false;
                },
                async create() {
                    try {
                        const staticData = this.getWorkflowStaticData("node");
                        const payload = await buildSubscriptionPayload(this);
                        const subscription = await subscribeTrigger(payload);
                        staticData.subscriptionId = subscription.subscription_id;
                        staticData.workflowId = payload.workflow_id;
                        staticData.nodeId = payload.node_id;
                        staticData.webhookMode = payload.webhook_mode;
                        return true;
                    } catch (error) {
                        console.error(`[TelegramMessageTrigger] create failed: ${error instanceof Error ? error.stack || error.message : String(error)}`);
                        throw error;
                    }
                },
                async delete() {
                    try {
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

                        await unsubscribeTrigger(unsubscribePayload);
                        delete staticData.subscriptionId;
                        delete staticData.workflowId;
                        delete staticData.nodeId;
                        delete staticData.webhookMode;
                        return true;
                    } catch (error) {
                        console.error(`[TelegramMessageTrigger] delete failed: ${error instanceof Error ? error.stack || error.message : String(error)}`);
                        throw error;
                    }
                },
            },
        };
    }

    async webhook() {
        const body = this.getBodyData();
        logToUi(
            this,
            "Telegram trigger received message",
            {
                source_title: body && body.source_title,
                source_id: body && body.source_id,
                message_id: body && body.message_id,
                text: body && body.text,
                media_count: Array.isArray(body && body.media_items) ? body.media_items.length : 0,
            },
        );
        return {
            workflowData: [this.helpers.returnJsonArray([body])],
        };
    }
}

exports.TelegramMessageTrigger = TelegramMessageTrigger;
