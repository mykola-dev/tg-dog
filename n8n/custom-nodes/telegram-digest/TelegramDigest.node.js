"use strict";

Object.defineProperty(exports, "__esModule", { value: true });
exports.TelegramDigest = void 0;

const { NodeConnectionTypes } = require("n8n-workflow");

const API_BASE_URL = process.env.TELEGRAM_SOURCE_SELECTOR_API_URL || "http://api:8000";
const DEFAULT_COMMAND = 'opencode run -m opencode/minimax-m2.5-free "{prompt}"';
const DEFAULT_SYSTEM_PROMPT = [
    "Create a compact Telegram digest from the provided messages.",
    "Group related updates by topic.",
    "Prioritize important developments.",
    "Avoid repetition.",
    "Preserve concrete facts, names, numbers, and links when present.",
    "Return Telegram-safe MarkdownV2 only.",
    "Formatting rules:",
    "- Use *bold* for section titles and important labels (single asterisk on each side).",
    "- Use _italic_ only for short source lists or light emphasis (single underscore on each side).",
    "- __underline__ means underline in MarkdownV2, not italic.",
    "- Use [text](url) for links and `code` only for literals.",
    "- Use simple bullet lists with '- '.",
    "- Do not use Markdown headings like # or ##.",
    "- Do not use HTML.",
    "- Do not use tables.",
    "- Do not use horizontal rules like ---.",
    "- Never use **bold** or __italic__ syntax.",
    "- Close every formatting marker correctly.",
].join("\n");
const DEFAULT_TITLE_TEMPLATE = '={{ "📰 ДАЙДЖЕСТ НОВИН ЗА " + $now.setLocale("uk").toFormat("d MMMM") }}';
const LEGACY_NOW_EXPRESSION_RE = /\{\{\s*\$now(?:\.setLocale\((['"])(.*?)\1\))?\.toFormat\((['"])(.*?)\3\)\s*\}\}/g;

function formatLegacyNowExpression(_match, _localeQuote, locale, _formatQuote, format) {
    const formatValue = String(format || "").trim();
    if (!formatValue) {
        return _match;
    }

    const date = new Date();
    const normalizedLocale = String(locale || "").trim() || undefined;
    const formatter = new Intl.DateTimeFormat(normalizedLocale, {
        day: "numeric",
        month: "long",
        year: "numeric",
    });
    const parts = formatter.formatToParts(date);
    const day = parts.find((part) => part.type === "day")?.value || String(date.getDate());
    const month = parts.find((part) => part.type === "month")?.value || formatter.format(date);
    const year = parts.find((part) => part.type === "year")?.value || String(date.getFullYear());

    const tokens = formatValue.match(/yyyy|MMMM|d|[^yMd]+/g);
    if (!tokens) {
        return _match;
    }
    return tokens
        .map((token) => {
            if (token === "yyyy") {
                return year;
            }
            if (token === "MMMM") {
                return month;
            }
            if (token === "d") {
                return day;
            }
            if (/[yMd]/.test(token)) {
                return _match;
            }
            return token;
        })
        .join("");
}

function normalizeTitleTemplate(rawValue) {
    const titleTemplate = String(rawValue || "").trim();
    if (!titleTemplate || !titleTemplate.includes("{{$now")) {
        return titleTemplate;
    }
    return titleTemplate.replace(LEGACY_NOW_EXPRESSION_RE, formatLegacyNowExpression);
}

async function createDigest(payload) {
    const response = await fetch(`${API_BASE_URL}/digest/messages`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    const body = await response.text();
    if (!response.ok) {
        throw new Error(`Telegram digest failed with status ${response.status}: ${body}`);
    }
    return body ? JSON.parse(body) : {};
}

class TelegramDigest {
    constructor() {
        this.description = {
            displayName: "TG Dog Digest",
            name: "telegramDigest",
            icon: "fa:list-alt",
            group: ["transform"],
            version: 1,
            description: "Generate a digest from cleaned Telegram messages using a CLI LLM worker",
            defaults: {
                name: "TG Dog Digest",
                color: "#7C3AED",
            },
            inputs: [NodeConnectionTypes.Main],
            outputs: [NodeConnectionTypes.Main],
            properties: [
                {
                    displayName: "Command Template",
                    name: "commandTemplate",
                    type: "string",
                    default: DEFAULT_COMMAND,
                    noDataExpression: true,
                    typeOptions: { rows: 2 },
                },
                {
                    displayName: "System Prompt",
                    name: "systemPrompt",
                    type: "string",
                    default: DEFAULT_SYSTEM_PROMPT,
                    noDataExpression: true,
                    typeOptions: { rows: 8 },
                },
                {
                    displayName: "Output Format",
                    name: "outputFormat",
                    type: "options",
                    default: "markdown_v2",
                    noDataExpression: true,
                    options: [
                        { name: "MarkdownV2", value: "markdown_v2" },
                        { name: "Plain Text", value: "plain_text" },
                    ],
                },
                {
                    displayName: "Include Title",
                    name: "includeTitle",
                    type: "boolean",
                    default: true,
                    noDataExpression: true,
                },
                {
                    displayName: "Title Template",
                    name: "titleTemplate",
                    type: "string",
                    default: DEFAULT_TITLE_TEMPLATE,
                    description: "Supports n8n expressions like ={{ \"📰 ДАЙДЖЕСТ НОВИН ЗА \" + $now.setLocale(\"uk\").toFormat(\"d MMMM\") }}",
                    typeOptions: { rows: 2 },
                    displayOptions: {
                        show: {
                            includeTitle: [true],
                        },
                    },
                },
            ],
        };
    }

    async execute() {
        const items = this.getInputData();
        const commandTemplate = String(this.getNodeParameter("commandTemplate", 0));
        const systemPrompt = String(this.getNodeParameter("systemPrompt", 0));
        const outputFormat = String(this.getNodeParameter("outputFormat", 0));
        const includeTitle = Boolean(this.getNodeParameter("includeTitle", 0));
        const titleTemplate = includeTitle ? normalizeTitleTemplate(this.getNodeParameter("titleTemplate", 0)) : "";

        const formattedText = items
            .map((item) => String((((item && item.json) || {}).formatted_text || ((item && item.json) || {}).combined_text || "")))
            .filter((entry) => entry.trim())
            .join("\n\n---\n\n");

        const digest = await createDigest({
            formatted_text: formattedText,
            command_template: commandTemplate,
            system_prompt: systemPrompt,
            output_format: outputFormat,
            title_text: titleTemplate,
        });
        return [[{ json: digest }]];
    }
}

exports.TelegramDigest = TelegramDigest;
