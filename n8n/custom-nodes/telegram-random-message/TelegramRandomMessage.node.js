"use strict";

Object.defineProperty(exports, "__esModule", { value: true });
exports.TelegramRandomMessage = void 0;

const { NodeConnectionTypes } = require("n8n-workflow");

const API_BASE_URL = process.env.TELEGRAM_SOURCE_SELECTOR_API_URL || "http://api:8000";

function logToUi(context, ...messages) {
    if (typeof context.sendMessageToUI !== "function") {
        return;
    }
    try {
        context.sendMessageToUI(...messages);
    } catch (_error) {
    }
}

function sortDialogs(dialogs) {
    return [...dialogs].sort((left, right) => {
        const leftDate = left.last_message_date || "";
        const rightDate = right.last_message_date || "";
        if (leftDate !== rightDate) {
            return rightDate.localeCompare(leftDate);
        }
        return String(left.name || "").localeCompare(String(right.name || ""));
    });
}

function formatDialogOptionName(dialog) {
    const lastMessageDate = dialog.last_message_date || "no recent message";
    return `${dialog.name} (${dialog.kind}) - ${lastMessageDate}`;
}

async function fetchDialogs() {
    const response = await fetch(`${API_BASE_URL}/dialogs`, {
        headers: {
            Accept: "application/json",
        },
    });
    const body = await response.text();

    if (!response.ok) {
        throw new Error(`Telegram dialogs request failed with status ${response.status}: ${body}`);
    }

    const payload = body ? JSON.parse(body) : [];
    if (!Array.isArray(payload)) {
        throw new Error(`Telegram dialogs response must be an array, got ${typeof payload}`);
    }

    return payload.map((dialog) => ({
        id: String(dialog.id),
        name: String(dialog.name),
        kind: String(dialog.kind),
        username: dialog.username ? String(dialog.username) : "",
        last_message_date: dialog.last_message_date || null,
    }));
}

async function fetchRandomMessage(dialogId, options) {
    const response = await fetch(`${API_BASE_URL}/messages/random`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            dialog_id: String(dialogId),
            skip_empty_text: Boolean(options.skipEmptyText),
            ignore_self: Boolean(options.ignoreSelf),
            ignore_service_messages: Boolean(options.ignoreServiceMessages),
        }),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Telegram random message read failed with status ${response.status}: ${body}`);
    }
    const payload = body ? JSON.parse(body) : null;
    if (!payload || Array.isArray(payload) || typeof payload !== "object") {
        throw new Error(`Telegram random message response must be an object, got ${typeof payload}`);
    }
    return payload;
}

class TelegramRandomMessage {
    constructor() {
        this.methods = {
            loadOptions: {
                async getSelectableDialogs() {
                    const dialogs = sortDialogs(await fetchDialogs());
                    return dialogs.map((dialog) => ({
                        name: formatDialogOptionName(dialog),
                        value: dialog.id,
                    }));
                },
            },
        };

        this.description = {
            displayName: "TG Dog Random Message",
            name: "telegramRandomMessage",
            icon: "fa:shuffle",
            group: ["transform"],
            version: 1,
            description: "Pick one random Telegram message from a selected dialog",
            defaults: {
                name: "TG Dog Random Message",
                color: "#0F766E",
            },
            inputs: [NodeConnectionTypes.Main],
            outputs: [NodeConnectionTypes.Main],
            properties: [
                {
                    displayName: "Dialog",
                    name: "dialogId",
                    type: "options",
                    default: "",
                    noDataExpression: true,
                    typeOptions: {
                        loadOptionsMethod: "getSelectableDialogs",
                    },
                },
                {
                    displayName: "Skip Empty Text",
                    name: "skipEmptyText",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                },
                {
                    displayName: "Ignore Self",
                    name: "ignoreSelf",
                    type: "boolean",
                    default: false,
                    noDataExpression: true,
                },
                {
                    displayName: "Ignore Service Messages",
                    name: "ignoreServiceMessages",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                },
            ],
        };
    }

    async execute() {
        const items = this.getInputData();
        const returnData = [];

        for (let itemIndex = 0; itemIndex < items.length; itemIndex += 1) {
            const dialogId = String(this.getNodeParameter("dialogId", itemIndex));
            const skipEmptyText = Boolean(this.getNodeParameter("skipEmptyText", itemIndex));
            const ignoreSelf = Boolean(this.getNodeParameter("ignoreSelf", itemIndex));
            const ignoreServiceMessages = Boolean(this.getNodeParameter("ignoreServiceMessages", itemIndex));

            if (!dialogId) {
                throw new Error("TG Dog Random Message requires a selected dialog");
            }

            const inputJson = ((items[itemIndex] && items[itemIndex].json) || {});
            const selectedMessage = await fetchRandomMessage(dialogId, {
                skipEmptyText,
                ignoreSelf,
                ignoreServiceMessages,
            });

            logToUi(
                this,
                "Telegram random message selected",
                {
                    source_title: selectedMessage.source_title,
                    source_id: selectedMessage.source_id,
                    message_id: selectedMessage.message_id,
                    text: selectedMessage.text,
                    media_count: Array.isArray(selectedMessage.media_items) ? selectedMessage.media_items.length : 0,
                },
            );

            returnData.push({
                json: {
                    ...inputJson,
                    ...selectedMessage,
                },
            });
        }

        return [returnData];
    }
}

exports.TelegramRandomMessage = TelegramRandomMessage;
