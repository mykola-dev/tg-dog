"use strict";

Object.defineProperty(exports, "__esModule", { value: true });
exports.MessagesCleanup = void 0;

const { NodeConnectionTypes } = require("n8n-workflow");

const API_BASE_URL = process.env.TELEGRAM_SOURCE_SELECTOR_API_URL || "http://api:8000";

async function cleanupMessages(payload) {
    const response = await fetch(`${API_BASE_URL}/messages/cleanup`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Messages cleanup failed with status ${response.status}: ${body}`);
    }
    return body ? JSON.parse(body) : {};
}

class MessagesCleanup {
    constructor() {
        this.description = {
            displayName: "TG Dog Messages Cleanup",
            name: "messagesCleanup",
            icon: "fa:align-left",
            group: ["transform"],
            version: 1,
            description: "Compact Telegram messages into reusable formatted text",
            defaults: {
                name: "TG Dog Messages Cleanup",
                color: "#0F766E",
            },
            inputs: [NodeConnectionTypes.Main],
            outputs: [NodeConnectionTypes.Main],
            properties: [
                {
                    displayName: "Mode",
                    name: "mode",
                    type: "options",
                    default: "combined",
                    noDataExpression: true,
                    options: [
                        { name: "Combined", value: "combined" },
                        { name: "Per Message", value: "per_message" },
                    ],
                },
                {
                    displayName: "Output Format",
                    name: "outputFormat",
                    type: "options",
                    default: "markdown",
                    noDataExpression: true,
                    options: [
                        { name: "Markdown", value: "markdown" },
                        { name: "Plain Text", value: "plain_text" },
                    ],
                },
                { displayName: "Include Source Title", name: "includeSourceTitle", type: "boolean", default: true, noDataExpression: true },
                { displayName: "Include Timestamp", name: "includeTimestamp", type: "boolean", default: true, noDataExpression: true },
                { displayName: "Include OCR Text", name: "includeOcrText", type: "boolean", default: true, noDataExpression: true },
                {
                    displayName: "Max Characters Per Message",
                    name: "maxCharactersPerMessage",
                    type: "number",
                    default: 1200,
                    noDataExpression: true,
                    typeOptions: { minValue: 80, maxValue: 10000, numberPrecision: 0 },
                },
            ],
        };
    }

    async execute() {
        const items = this.getInputData();
        const mode = String(this.getNodeParameter("mode", 0));
        const outputFormat = String(this.getNodeParameter("outputFormat", 0));
        const includeSourceTitle = Boolean(this.getNodeParameter("includeSourceTitle", 0));
        const includeTimestamp = Boolean(this.getNodeParameter("includeTimestamp", 0));
        const includeOcrText = Boolean(this.getNodeParameter("includeOcrText", 0));
        const maxCharactersPerMessage = Number(this.getNodeParameter("maxCharactersPerMessage", 0));

        const messages = items.map((item) => ({ ...((item && item.json) || {}) }));
        const payload = await cleanupMessages({
            messages,
            mode,
            output_format: outputFormat,
            include_source_title: includeSourceTitle,
            include_timestamp: includeTimestamp,
            include_ocr_text: includeOcrText,
            max_characters_per_message: maxCharactersPerMessage,
        });

        if (mode === "combined") {
            return [[{ json: payload }]];
        }

        const returnData = (payload.formatted_messages || []).map((item) => ({
            json: {
                source_id: item.source_id,
                message_id: item.message_id,
                formatted_text: item.formatted_text,
                output_format: payload.output_format,
            },
        }));
        return [returnData];
    }
}

exports.MessagesCleanup = MessagesCleanup;
