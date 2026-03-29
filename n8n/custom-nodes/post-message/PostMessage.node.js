"use strict";

Object.defineProperty(exports, "__esModule", { value: true });
exports.PostMessage = void 0;

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

async function fetchSendTargets(senderMode) {
    const response = await fetch(`${API_BASE_URL}/dialogs/send-targets?sender_mode=${encodeURIComponent(senderMode)}`, {
        headers: { Accept: "application/json" },
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Telegram send targets request failed with status ${response.status}: ${body}`);
    }
    const payload = body ? JSON.parse(body) : [];
    return Array.isArray(payload) ? payload : [];
}

async function postMessage(payload) {
    const response = await fetch(`${API_BASE_URL}/post/message`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Post message failed with status ${response.status}: ${body}`);
    }
    return body ? JSON.parse(body) : {};
}

function resolveMessageText(payload, preferredFieldName) {
    const candidates = [
        preferredFieldName,
        "digest_text",
        "combined_text",
        "formatted_text",
        "text",
    ];

    for (const fieldName of candidates) {
        const value = payload[fieldName];
        if (typeof value === "string" && value.trim()) {
            return value;
        }
    }

    return "";
}

function resolveDeliveryChunks(payload) {
    if (!Array.isArray(payload.delivery_chunks)) {
        return [];
    }
    return payload.delivery_chunks.filter((chunk) => typeof chunk === "string" && chunk.trim());
}

function resolvePrimaryMedia(payload) {
    const mediaItems = Array.isArray(payload.media_items) ? payload.media_items : [];
    for (const item of mediaItems) {
        if (!item || typeof item !== "object") {
            continue;
        }
        const fileRef = typeof item.file_ref === "string" ? item.file_ref.trim() : "";
        if (!fileRef) {
            continue;
        }
        return {
            media_file_ref: fileRef,
            media_mime_type: typeof item.mime_type === "string" ? item.mime_type : null,
            media_kind: typeof item.media_kind === "string" ? item.media_kind : null,
        };
    }
    return null;
}

class PostMessage {
    constructor() {
        this.methods = {
            loadOptions: {
                async getSendTargets() {
                    const senderMode = String(this.getNodeParameter("senderMode") || "user");
                    const targets = await fetchSendTargets(senderMode);
                    return targets.map((target) => ({
                        name: `${target.name} (${target.kind})`,
                        value: String(target.id),
                    }));
                },
            },
        };

        this.description = {
            displayName: "TG Dog Post Message",
            name: "postMessage",
            icon: "fa:paper-plane",
            group: ["transform"],
            version: 1,
            description: "Send prepared text to a selected Telegram target",
            defaults: {
                name: "TG Dog Post Message",
                color: "#DC2626",
            },
            inputs: [NodeConnectionTypes.Main],
            outputs: [NodeConnectionTypes.Main],
            properties: [
                {
                    displayName: "Sender",
                    name: "senderMode",
                    type: "options",
                    default: "user",
                    noDataExpression: true,
                    options: [
                        { name: "My Account", value: "user" },
                        { name: "Bot", value: "bot" },
                    ],
                },
                {
                    displayName: "Bot mode uses the global TELEGRAM_BOT_TOKEN from .env. There is no per-node bot ID field in this version.",
                    name: "botModeNotice",
                    type: "notice",
                    default: "",
                    displayOptions: {
                        show: {
                            senderMode: ["bot"],
                        },
                    },
                },
                {
                    displayName: "Target",
                    name: "targetId",
                    type: "options",
                    default: "self",
                    noDataExpression: true,
                    typeOptions: {
                        loadOptionsMethod: "getSendTargets",
                        loadOptionsDependsOn: ["senderMode"],
                    },
                    description: "In Bot mode, delivery may fail if the bot is not a member/admin of the selected target.",
                },
                {
                    displayName: "Delivery Mode",
                    name: "deliveryMode",
                    type: "options",
                    default: "auto",
                    noDataExpression: true,
                    options: [
                        {
                            name: "Auto",
                            value: "auto",
                            description: "Use forward when source_id/message_id are present, otherwise send text/media normally",
                        },
                        {
                            name: "Send",
                            value: "send",
                            description: "Send the prepared text/media payload directly",
                        },
                        {
                            name: "Forward",
                            value: "forward",
                            description: "Forward the original Telegram message when source metadata is present",
                        },
                        {
                            name: "Copy",
                            value: "copy",
                            description: "Repost the original Telegram message without forward header when source metadata is present",
                        },
                    ],
                },
                {
                    displayName: "Input Field Name",
                    name: "inputFieldName",
                    type: "string",
                    default: "digest_text",
                    noDataExpression: true,
                },
                {
                    displayName: "Format",
                    name: "parseMode",
                    type: "options",
                    default: "plain_text",
                    noDataExpression: true,
                    options: [
                        { name: "Plain Text", value: "plain_text" },
                        { name: "MarkdownV2", value: "markdown_v2" },
                    ],
                },
            ],
        };
    }

    async execute() {
        const items = this.getInputData();
        const returnData = [];
        for (let itemIndex = 0; itemIndex < items.length; itemIndex += 1) {
            const senderMode = String(this.getNodeParameter("senderMode", itemIndex));
            const targetId = String(this.getNodeParameter("targetId", itemIndex));
            const deliveryMode = String(this.getNodeParameter("deliveryMode", itemIndex));
            const inputFieldName = String(this.getNodeParameter("inputFieldName", itemIndex));
            const configuredParseMode = String(this.getNodeParameter("parseMode", itemIndex));
            const payload = (items[itemIndex] && items[itemIndex].json) || {};
            const text = resolveMessageText(payload, inputFieldName);
            const deliveryChunks = resolveDeliveryChunks(payload);
            const parseMode = typeof payload.parse_mode === "string" && payload.parse_mode.trim()
                ? payload.parse_mode.trim()
                : configuredParseMode;
            const media = resolvePrimaryMedia(payload);
            if (!deliveryChunks.length && !text.trim() && !media) {
                throw new Error(
                    `Post Message could not find sendable text, delivery chunks, or media in fields: delivery_chunks, ${inputFieldName}, digest_text, combined_text, formatted_text, text, media_items`,
                );
            }
            const result = await postMessage({
                sender_mode: senderMode,
                delivery_mode: deliveryMode,
                target_id: targetId,
                text,
                parse_mode: parseMode,
                delivery_chunks: deliveryChunks,
                media_file_ref: media ? media.media_file_ref : null,
                media_mime_type: media ? media.media_mime_type : null,
                media_kind: media ? media.media_kind : null,
                source_id: typeof payload.source_id === "string" ? payload.source_id : null,
                source_message_id: typeof payload.message_id === "string" ? payload.message_id : null,
            });
            logToUi(
                this,
                "Post Message delivery result",
                {
                    target_id: targetId,
                    sender_mode: senderMode,
                    text_preview: text ? text.slice(0, 120) : "",
                    chunk_count: deliveryChunks.length,
                    media_kind: media ? media.media_kind : null,
                    delivery_status: result.delivery_status,
                    sent_message_refs: result.sent_message_refs,
                },
            );
            returnData.push({ json: { ...payload, ...result } });
        }
        return [returnData];
    }
}

exports.PostMessage = PostMessage;
