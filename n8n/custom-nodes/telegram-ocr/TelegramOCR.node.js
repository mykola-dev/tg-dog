"use strict";

Object.defineProperty(exports, "__esModule", { value: true });
exports.TelegramOCR = void 0;

const { NodeConnectionTypes } = require("n8n-workflow");

const API_BASE_URL = process.env.TELEGRAM_SOURCE_SELECTOR_API_URL || "http://api:8000";

async function enrichMessages(messages) {
    const response = await fetch(`${API_BASE_URL}/ocr/messages`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            messages,
        }),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`TG Dog OCR failed with status ${response.status}: ${body}`);
    }
    const payload = body ? JSON.parse(body) : [];
    if (!Array.isArray(payload)) {
        throw new Error(`TG Dog OCR response must be an array, got ${typeof payload}`);
    }
    return payload;
}

class TelegramOCR {
    constructor() {
        this.description = {
            displayName: "TG Dog OCR",
            name: "telegramOCR",
            icon: "fa:file-image-o",
            group: ["transform"],
            version: 1,
            description: "Extract text from Telegram image attachments with local tesseract OCR",
            defaults: {
                name: "TG Dog OCR",
                color: "#D97706",
            },
            inputs: [NodeConnectionTypes.Main],
            outputs: [NodeConnectionTypes.Main],
            properties: [
            ],
        };
    }

    async execute() {
        const items = this.getInputData();
        const messages = items.map((item) => ({ ...((item && item.json) || {}) }));
        if (!messages.length) {
            return [[]];
        }
        const enriched = await enrichMessages(messages);
        return [enriched.map((message) => ({ json: message }))];
    }
}

exports.TelegramOCR = TelegramOCR;
