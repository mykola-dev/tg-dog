# Quickstart

## 1) Prepare environment

```bash
cp .env.example .env
```

Replace the placeholder secrets before first boot.

Set at least:

- `POSTGRES_PASSWORD`
- `APP_MASTER_KEY`

Optional:

- `TELEGRAM_BOT_TOKEN` if you want bot delivery or bot-command triggers
- `TELEGRAM_BOT_WEBHOOK_BASE_URL` if you want bot-command webhook mode through the backend API
- `WEBHOOK_URL` if you want public `n8n` webhooks for other flows

Recommended for stable interactive onboarding:

- `COMPOSE_MENU=false`

## 2) Start the stack

```bash
make up
```

`make up` runs `docker compose up -d --build --wait --remove-orphans` and then attaches the Telegram onboarding flow inside `api`.

Named Docker volumes are created automatically on first start.
If you previously ran an older stack shape, `make up` also removes orphaned containers from the old compose topology.

## 3) Open n8n

- URL: `http://localhost:50000`
- On a fresh `n8n_data` volume, complete the standard `n8n` first-run owner setup in the browser.
- On later restarts, log in with the owner email and password you created there.

## 4) Confirm the workspace is empty but ready

- The stack does not preload repo-managed workflows.
- New workflows you create in the UI are stored by `n8n` and should survive restart.
- Start with `New Workflow`.

## 5) Connect Telegram account

Follow these in order:

- `docs/user/telegram-app-setup.md`
- `docs/user/connect-account.md`

## 6) Run first digest

Before using the AI text step, log in inside the API container:

```bash
make login-opencode
```

That local OpenCode runtime inside `api` is the current AI text-processing path used by the built-in `HTTP Request -> /ai/text` flow.

Then build the first workflow.

## 7) Build the first workflow

Simple path:

1. Create a workflow in `n8n`.
2. Add `Manual Trigger`.
3. Add `TG Dog Source Selector`.
4. Add built-in `HTTP Request` to `POST http://api:8000/messages/read`.
5. Send JSON with `dialog_ids`, `lookback_hours`, and `include_media`.
6. Optionally add built-in `HTTP Request` to `POST http://api:8000/ocr/messages`.
7. If you want one OCR request for many message items, aggregate them first with built-in `Item Lists`.
8. Use built-in `Code` or other standard transform nodes to prepare text.
9. Add built-in `HTTP Request` to `POST http://api:8000/ai/text` for the AI step.
10. Add built-in `Code` if you need HTML chunking or delivery shaping.
11. Add `TG Dog Post Message` for delivery.

Useful variations:

- set `include_media = false` in the read request for faster text-only reads
- use `TG Dog Source Selector -> IF -> HTTP Request /messages/random` if you want one random real message from a selected dialog
- use `TG Dog Message Trigger` for realtime user-account message workflows
- use `TG Dog Bot Command Trigger` if you want a bot command like `/run` to start the workflow

## 8) Bot-command trigger notes

- `TG Dog Bot Command Trigger` uses the backend Bot API runtime, not the Telethon message listener
- webhook mode needs `TELEGRAM_BOT_TOKEN` plus a public HTTPS base URL for the `api` service
- set a stable default in `.env` with `TELEGRAM_BOT_WEBHOOK_BASE_URL=https://<public-host>`
- if no webhook base URL is available, the backend can fall back to polling mode
- temporary runtime overrides go through `POST /telegram-bot-commands/config`
- return control to `.env` with `POST /telegram-bot-commands/config` and `{ "use_env": true }`

For the node-by-node walkthrough, see `docs/user/run-workflow-in-n8n.md`.
For HTTP node details and payload-shaping guidance, see `docs/user/run-workflow-in-n8n.md`.

## Security notes

- Do not commit `.env`, `telegram_sessions`, `run_artifacts`, or exported Docker volume data.
- Telegram session state and worker auth are meant to stay in Docker volumes, not in tracked files.

## Reset all data

To wipe the full local stack state and start from scratch:

```bash
make reset-data
```

That removes containers plus all named Docker volumes for Postgres, `n8n`, Telegram sessions, run artifacts, and worker auth.
