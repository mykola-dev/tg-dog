# Run a Workflow in n8n

This guide covers the current user-owned `n8n` workflow path.

## Available nodes

- `TG Dog Source Selector`
- `TG Dog Message Trigger`
- `TG Dog Bot Command Trigger`
- `TG Dog Post Message`

Notes:

- `TG Dog Message Trigger` is the Telethon user-account realtime path.
- `TG Dog Bot Command Trigger` is a separate Bot API ingress path.

## Build a workflow

- Before using the AI text step, log in once inside the API container:

```bash
docker compose exec -it api opencode providers login
```

- Create a new workflow in `n8n`.
- Add `Manual Trigger`.
- Add `TG Dog Source Selector`.
- Select one or more dialogs.
- Add built-in `HTTP Request` after the selector to call `POST http://api:8000/messages/read`.
- Set `lookback_hours` in the request body.
- Set `include_media = false` if you want a faster text-only read and do not need OCR candidates.
- Or use `TG Dog Source Selector -> IF -> HTTP Request /messages/random` when you want one random real Telegram message from a selected dialog.
- Or use `TG Dog Message Trigger` when you need real-time reactions to new messages from one selected Telegram dialog.
- `TG Dog Message Trigger` is `Telethon`-based and intended for user-account message listening, not bot updates.
- Use `TG Dog Bot Command Trigger` when you want a workflow to start from a Telegram bot command like `/run`.
- Configure its `Command` parameter directly in the node.
- By default it only allows commands from the currently connected Telegram account.
- Keep `Require Private Chat` enabled when the bot command should work only in a direct chat with the bot.
- `TG Dog Bot Command Trigger` uses the backend Bot API ingress path, not the user-account `Telethon` listener.
- To use webhook mode, set `TELEGRAM_BOT_TOKEN` and provide a public HTTPS base URL for the `api` service.
- You can keep a stable default in `.env` with `TELEGRAM_BOT_WEBHOOK_BASE_URL`, or apply a temporary runtime override through `POST /telegram-bot-commands/config`.
- To hand control back to `.env`, call `POST /telegram-bot-commands/config` with `{ "use_env": true }`.
- If you explicitly switch the runtime override to polling mode, the backend falls back to real Bot API long polling for bot commands.
- In webhook mode Telegram hits `/telegram-bot-commands/webhook` on that public base URL.
- `TG Dog Message Trigger` keeps using `N8N_INTERNAL_WEBHOOK_BASE_URL`, so user-account realtime flows do not depend on the public bot webhook tunnel.
- Add built-in `HTTP Request` after the reader when you want OCR enrichment.
- Call `POST http://api:8000/ocr/messages` with the reader output as `messages`.
- Use built-in `Code`, `Edit Fields`, or other standard transform nodes after OCR when you need cleanup, formatting, field reshaping, or prompt preparation.
- Add built-in `HTTP Request` if you want an OpenCode-backed AI text step.
- Call `POST http://api:8000/ai/text` with a `prompt`, optional `system_prompt`, and `command_template`.
- Add built-in `Code` after that when you need to split large HTML output into delivery-ready chunks.
- Add `TG Dog Post Message` if you want to send the cleaned text or AI output to Telegram.

### AI text with built-in nodes

- Use built-in `HTTP Request`.
- Method: `POST`.
- URL: `http://api:8000/ai/text`.
- Send body as JSON.
- Example body:

```json
{
  "prompt": {{$json.prompt}},
  "system_prompt": {{$json.system_prompt}},
  "command_template": "opencode run -m opencode/minimax-m2.5-free \"{prompt}\""
}
```

- Use built-in `Code` after `/ai/text` when you need to:
  - add a title
  - split long HTML into delivery chunks
  - set `parse_mode = html`
  - map output into the fields expected by `TG Dog Post Message`

### Read messages with built-in nodes

- Use built-in `HTTP Request`.
- Method: `POST`.
- URL: `http://api:8000/messages/read`.
- Send body as JSON.
- Example body after `TG Dog Source Selector`:

```json
{
  "dialog_ids": {{$json.selected_dialog_ids}},
  "lookback_hours": 24,
  "include_media": true
}
```

- `lookback_hours` is the explicit lookback window in hours.
- `include_media` controls whether supported image attachments are downloaded for OCR.
- If `include_media = true`, set a higher `HTTP Request` timeout because media-backed reads can take much longer than text-only reads.
- A practical baseline is `180000` ms for media-enabled reads.
- The endpoint returns one canonical message item per Telegram message.

### OCR with built-in nodes

- Use `HTTP Request`.
- Method: `POST`.
- URL: `http://api:8000/ocr/messages`.
- Send body as JSON.

If your previous node already outputs a single item with a `messages` array field, use this body:

```json
{{$json}}
```

If your previous node outputs one canonical message per item, collect them into one item first, then use this body:

```json
{
  "messages": {{$json.messages}}
}
```

- Recommended collect step before OCR when you have many incoming items:
  - use built-in `Item Lists`
  - `Operation`: `Concatenate Items`
  - `Aggregate`: `All Item Data (Into a Single List)`
  - `Put Output in Field`: `messages`
- Why: `HTTP Request` executes once per input item. If you want one OCR API call for the whole set, collect the messages first.
- If you skip collect on multi-item input, `HTTP Request` can repeat the request once per item.
- The OCR runtime still lives in `api`, where `tesseract` is installed.
- Do not plan on local OCR execution inside `n8n` unless the container runtime is changed on purpose.

### Our HTTP API patterns

- `/ocr/messages`
  - expects one JSON object with `messages: [...]`
  - use collect first if your workflow currently has one message per item
- `/messages/read`
  - expects `dialog_ids`, `lookback_hours`, and optional `include_media`
  - returns one canonical message item per Telegram message
- `/messages/random`
  - expects a single `dialog_id`
  - use `TG Dog Source Selector` plus an `IF` node to enforce exactly one selected dialog before the request
- `/ai/text`
  - send one JSON object with `prompt`
  - optionally include `system_prompt`
  - include `command_template` when you want explicit OpenCode invocation control
- built-in `Code`
  - use it after `/ai/text` when you need Telegram-safe HTML chunking or custom delivery shaping
- `/post/message`
  - usually send one item per outgoing Telegram delivery action
  - do not collect multiple outbound posts into one request unless the endpoint contract explicitly expects it

Rule of thumb:

- collect before `HTTP Request` when the API expects one batch object
- do not collect when the API expects one request per item

### Cleanup with built-in nodes

- There is no longer a dedicated cleanup custom node.
- Use built-in nodes to do exactly the formatting you need.
- For small field reshapes, prefer `Edit Fields`, `Set`, `Merge`, or expressions.
- For message-to-text conversion or custom prompt assembly, use a `Code` node.
- Keep the cleanup logic close to the workflow that actually needs it, unless it becomes a reusable sub-workflow on purpose.

## Delivery notes

- `TG Dog Post Message -> Sender = My Account` sends through your connected Telegram user session.
- `TG Dog Post Message -> Sender = Bot` sends through `TELEGRAM_BOT_TOKEN` using the Telegram Bot API.
- AI output is not auto-chunked by the backend anymore; shape and split it in built-in workflow logic before delivery when needed.
- `TG Dog Post Message -> Format` should now be either `Plain Text` or `HTML`.
- `Forward` and `Copy` need Telegram-origin items with `source_id` and `message_id`.
- In `Bot` mode the target dropdown reuses your Telegram dialog list except `Saved Messages`.
- Bot delivery can still fail if the bot is not a member or lacks required rights in the selected target.
