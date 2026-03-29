"use strict";

Object.defineProperty(exports, "__esModule", { value: true });
exports.TelegramSourceSelector = void 0;

const { NodeConnectionTypes } = require("n8n-workflow");

const API_BASE_URL = process.env.TELEGRAM_SOURCE_SELECTOR_API_URL || "http://api:8000";
const SOURCE_KIND_OPTIONS = [
    {
        name: "Channels",
        value: "channel",
    },
    {
        name: "Groups",
        value: "group",
    },
    {
        name: "Contacts",
        value: "contact",
    },
];

function normalizeMultiValue(value, fallback = []) {
    if (Array.isArray(value)) {
        return value.map((entry) => String(entry));
    }
    if (value === undefined || value === null || value === "") {
        return [...fallback];
    }
    return [String(value)];
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

function filterDialogsByKinds(dialogs, includeKinds) {
    if (!includeKinds.length) {
        return dialogs;
    }

    const allowedKinds = new Set(includeKinds);
    return dialogs.filter((dialog) => allowedKinds.has(String(dialog.kind)));
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
        can_send: Boolean(dialog.can_send),
    }));
}

class TelegramSourceSelector {
    constructor() {
        this.methods = {
            loadOptions: {
                async getSelectableDialogs() {
                    const includeKinds = normalizeMultiValue(
                        this.getCurrentNodeParameter("includeKinds"),
                        SOURCE_KIND_OPTIONS.map((option) => option.value),
                    );
                    const dialogs = filterDialogsByKinds(sortDialogs(await fetchDialogs()), includeKinds);

                    return dialogs.map((dialog) => ({
                        name: formatDialogOptionName(dialog),
                        value: dialog.id,
                    }));
                },
            },
        };

        this.description = {
            displayName: "TG Dog Source Selector",
            name: "telegramSourceSelector",
            icon: "fa:telegram",
            group: ["transform"],
            version: 1,
            description: "Select Telegram dialogs from the connected account",
            defaults: {
                name: "TG Dog Source Selector",
                color: "#229ED9",
            },
            inputs: [NodeConnectionTypes.Main],
            outputs: [NodeConnectionTypes.Main],
            properties: [
                {
                    displayName: "Include Kinds",
                    name: "includeKinds",
                    type: "multiOptions",
                    noDataExpression: true,
                    default: SOURCE_KIND_OPTIONS.map((option) => option.value),
                    options: SOURCE_KIND_OPTIONS,
                },
                {
                    displayName: "Selected Dialogs",
                    name: "selectedDialogIds",
                    type: "multiOptions",
                    noDataExpression: true,
                    default: [],
                    typeOptions: {
                        loadOptionsDependsOn: ["includeKinds"],
                        loadOptionsMethod: "getSelectableDialogs",
                    },
                },
            ],
        };
    }

    async execute() {
        const items = this.getInputData();
        const dialogs = sortDialogs(await fetchDialogs());
        const dialogsById = new Map(dialogs.map((dialog) => [dialog.id, dialog]));
        const returnData = [];

        for (let itemIndex = 0; itemIndex < items.length; itemIndex += 1) {
            const selectedDialogIds = normalizeMultiValue(this.getNodeParameter("selectedDialogIds", itemIndex), []);
            const selectedDialogs = selectedDialogIds
                .map((dialogId) => dialogsById.get(String(dialogId)))
                .filter((dialog) => dialog !== undefined);

            returnData.push({
                json: {
                    ...((items[itemIndex] && items[itemIndex].json) || {}),
                    selected_dialog_ids: selectedDialogIds,
                    selected_dialogs: selectedDialogs,
                },
            });
        }

        return [returnData];
    }
}

exports.TelegramSourceSelector = TelegramSourceSelector;
