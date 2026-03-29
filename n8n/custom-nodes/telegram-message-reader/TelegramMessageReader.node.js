"use strict";

Object.defineProperty(exports, "__esModule", { value: true });
exports.TelegramMessageReader = void 0;

const { NodeConnectionTypes } = require("n8n-workflow");

const API_BASE_URL = process.env.TELEGRAM_SOURCE_SELECTOR_API_URL || "http://api:8000";

function normalizeSelectedDialogIds(itemJson) {
    const value = itemJson && itemJson.selected_dialog_ids;
    if (!Array.isArray(value)) {
        return [];
    }
    return value.map((entry) => String(entry));
}

async function fetchMessages(dialogIds, lookbackHours, includeMedia) {
    const response = await fetch(`${API_BASE_URL}/messages/read`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            dialog_ids: dialogIds,
            lookback_hours: lookbackHours,
            include_media: includeMedia,
        }),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Telegram message read failed with status ${response.status}: ${body}`);
    }
    const payload = body ? JSON.parse(body) : [];
    if (!Array.isArray(payload)) {
        throw new Error(`Telegram message read response must be an array, got ${typeof payload}`);
    }
    return payload;
}

class TelegramMessageReader {
    constructor() {
        this.description = {
            displayName: "TG Dog Message Reader",
            name: "telegramMessageReader",
            icon: "fa:telegram",
            group: ["transform"],
            version: 1,
            description: "Read recent Telegram messages for selected dialogs",
            defaults: {
                name: "TG Dog Message Reader",
                color: "#229ED9",
            },
            inputs: [NodeConnectionTypes.Main],
            outputs: [NodeConnectionTypes.Main],
            properties: [
                {
                    displayName: "Lookback Hours",
                    name: "lookbackHours",
                    type: "number",
                    default: 24,
                    noDataExpression: true,
                    typeOptions: {
                        minValue: 1,
                        maxValue: 24 * 30,
                        numberPrecision: 0,
                    },
                    description: "Read messages from the last N hours",
                },
                {
                    displayName: "Include Media",
                    name: "includeMedia",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                    description: "Download image attachments for downstream OCR. Disable for faster text-only reads.",
                },
            ],
        };
    }

    async execute() {
        const items = this.getInputData();
        const returnData = [];

        for (let itemIndex = 0; itemIndex < items.length; itemIndex += 1) {
            const lookbackHours = Number(this.getNodeParameter("lookbackHours", itemIndex));
            const includeMedia = Boolean(this.getNodeParameter("includeMedia", itemIndex));
            const inputJson = ((items[itemIndex] && items[itemIndex].json) || {});
            const selectedDialogIds = normalizeSelectedDialogIds(inputJson);
            if (!selectedDialogIds.length) {
                continue;
            }
            const messages = await fetchMessages(selectedDialogIds, lookbackHours, includeMedia);
            for (const message of messages) {
                returnData.push({
                    json: {
                        ...message,
                    },
                });
            }
        }

        return [returnData];
    }
}

exports.TelegramMessageReader = TelegramMessageReader;
