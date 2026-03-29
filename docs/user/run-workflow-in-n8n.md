# Run a Workflow in n8n

This guide covers the current user-owned `n8n` workflow path.

## Available nodes

- `TG Dog Source Selector`
- `TG Dog Message Reader`
- `TG Dog Message Trigger`
- `TG Dog Bot Command Trigger`
- `TG Dog Random Message`
- `TG Dog OCR`
- `TG Dog Messages Cleanup`
- `TG Dog Digest`
- `TG Dog Post Message`

## Build a workflow

- Before using `TG Dog Digest`, log in once inside the OpenCode worker:

```bash
docker compose exec -it opencode-worker opencode providers login
```

- Create a new workflow in `n8n`.
- Add `Manual Trigger`.
- Add `TG Dog Source Selector`.
- Select one or more dialogs.
- Add `TG Dog Message Reader` after the selector.
- Set `Lookback Hours`.
- Disable `Include Media` if you want a faster text-only read and do not need OCR candidates.
- Or use `TG Dog Random Message` when you want one random real Telegram message from the selected dialog history.
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
- Add `TG Dog OCR` after the reader when you want OCR enrichment.
- Add `TG Dog Messages Cleanup` after OCR.
- Add `TG Dog Digest` if you want an LLM digest.
- Add `TG Dog Post Message` if you want to send the cleaned text or digest to Telegram.

## Delivery notes

- `TG Dog Post Message -> Sender = My Account` sends through your connected Telegram user session.
- `TG Dog Post Message -> Sender = Bot` sends through `TELEGRAM_BOT_TOKEN` using the Telegram Bot API.
- Digest output is prepared for Telegram in the digest step itself and emitted as delivery-ready chunks.
- `TG Dog Post Message -> Format = MarkdownV2` is currently supported only for `Sender = Bot`.
- `Forward` and `Copy` need Telegram-origin items with `source_id` and `message_id`.
- In `Bot` mode the target dropdown reuses your Telegram dialog list except `Saved Messages`.
- Bot delivery can still fail if the bot is not a member or lacks required rights in the selected target.
