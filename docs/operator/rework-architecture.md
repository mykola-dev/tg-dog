# Rework Architecture

This document is the current source of truth for the `n8n` rework and supersedes older bootstrap-era workflow assumptions.

## Product direction

- Keep Telegram account onboarding in CLI with real `Telethon` user-session auth.
- Use `n8n` as the control plane, workflow editor, and scheduler.
- Prefer standard `n8n` nodes where they fit, but build thin custom nodes for Telegram user-account workflows.
- Avoid code editing in workflow UX; user-facing configuration should live in node parameters.
- Treat repo-managed workflow preloads as deprecated. User-created workflows are the persistent runtime unit now.

## Runtime model

- `postgres` stores relational state.
- `n8n` stores workflow definitions and executions in `n8n_data`.
- `api` exposes real HTTP endpoints for Telegram-backed custom nodes.
- `app` hosts shared Python runtime and CLI adapters.
- `Telethon` is the real integration path for Telegram account state, dialog listing, and message history reads.

## Workflow ownership

- The stack bootstraps only the initial `n8n` owner account.
- The stack does not import or reconcile repo-managed workflows on startup.
- Workflows created in the `n8n` UI or via the `n8n` API must persist across restart through the `n8n_data` volume.
- Restart must never overwrite user-edited workflows.

## Canonical message contract

All downstream content-processing nodes should converge on one message shape regardless of source.

Required fields:

- `schema_version`
- `source_kind`
- `source_id`
- `source_title`
- `message_id`
- `message_timestamp`
- `text`
- `is_outbound`
- `is_from_self`
- `is_service_message`
- `media_items`
- `ingestion_meta`

Media item rules:

- `media_kind=image` is the only media kind the first OCR flow must consume.
- Video, audio, and non-image documents are ignored by the first message-reader node.
- Image attachments should carry `ocr_status=pending` until OCR processing runs.

## Node roadmap

### Available now

- `TG Dog Source Selector`
  - Reads live dialogs from the connected Telegram account.
  - Persists selected dialog ids in workflow parameters.
  - Refreshes labels and metadata live at execution time.

- `TG Dog Message Reader`
  - Reads recent message history for selected dialogs via the `api` bridge.
  - Uses real `Telethon` history reads.
  - Returns one `n8n` item per message.
  - Keeps only text and image attachments in the first version.
  - Marks image attachments with `ocr_status=pending` for the OCR step.

- `TG Dog Message Trigger`
  - Registers a real-time `Telethon` listener for one selected dialog.
  - Pushes canonical message items into `n8n` through a trigger webhook.
  - Keeps image attachments so downstream OCR can run in trigger-driven workflows.
  - Rewrites webhook destinations to `N8N_INTERNAL_WEBHOOK_BASE_URL`, so user-account realtime flows do not depend on any public bot-webhook tunnel.

- `TG Dog Bot Command Trigger`
  - Registers a bot-command subscription through the backend Bot API webhook runtime.
  - Starts workflows from Telegram bot commands like `/run` without abusing `Schedule Trigger` as an external entrypoint.
  - Keeps bot-command ingress separate from `Telethon` user-account ingress.

- `TG Dog Random Message`
  - Picks one random canonical message from the full history of one selected dialog.
  - Can surface text, images, and supported GIF-style media for downstream delivery flows.

- `TG Dog OCR`
  - Reads canonical message items.
  - Uses real local `tesseract` through the backend OCR path.
  - Enriches image media in place with OCR text and status fields.
  - Leaves non-image media skipped.

- `TG Dog Messages Cleanup`
  - Compacts canonical message items into reusable formatted text.
  - Supports combined digest input and per-message posting input.

- `TG Dog Digest`
  - Calls a real CLI LLM worker through the backend digest path.
  - Defaults to `OpenCode` command execution in the worker container.
  - Normalizes digest output into Telegram-safe `MarkdownV2` and emits pre-split `delivery_chunks` for bot delivery.

- `TG Dog Post Message`
  - Sends prepared text to Telegram through the real user-session path.
  - Supports direct send plus Telegram-native forward/copy repost modes for canonical items that still carry `source_id` and `message_id`.
  - Consumes pre-split digest `delivery_chunks` without re-chunking markdown content.
  - Defaults to `Saved Messages` but can target writable dialogs.

### Next

- `TG Dog OCR`
  - Input: canonical message items
  - Runs real `tesseract` over image attachments only
  - Produces enriched message items without requiring manual code edits in `n8n`

- `Telegram Filter`
  - Input: canonical message items
  - Applies local blacklist/whitelist logic

- `Telegram Filter`
  - Input: canonical message items
  - Applies local blacklist/whitelist logic before cleanup/digest/post flows

## Compatibility stance

- Core Telegram history workflows are `Telethon`-first, not Telegram Bot API first.
- Built-in `n8n` Telegram bot nodes are optional side integrations.
- `TG Dog Bot Command Trigger` is the intended bot-command ingress path for `/run` style controls.
- Bot-command ingress and user-account `Telethon` ingress are intentionally separate paths.
- If bot-trigger payloads need to flow into OCR/filter/digest later, add a normalizer node that converts them into the canonical message contract.
- Do not distort the core contract to mirror Bot API payloads.

## Current node chains

- Digest path: `TG Dog Source Selector -> TG Dog Message Reader -> TG Dog OCR -> TG Dog Messages Cleanup -> TG Dog Digest -> TG Dog Post Message`
- Direct post path: `TG Dog Message Reader or future trigger -> TG Dog OCR -> TG Dog Messages Cleanup -> TG Dog Post Message`
- Real-time reply path: `TG Dog Message Trigger -> Filter -> reply selection -> TG Dog Post Message`

## Documentation policy

- `rework.md` is the ideation seed.
- This document is the structured architecture reference derived from it.
- User docs and operator docs must be updated in the same milestone as runtime changes.
- Remove or rewrite docs that describe obsolete repo-managed workflows or the pre-rework frontend-first direction.
