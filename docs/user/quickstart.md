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

`make up` runs `docker compose up -d --build --wait` and then attaches the Telegram onboarding flow inside `app`.

Named Docker volumes are created automatically on first start.

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

Before using `TG Dog Digest`, log in inside the worker:

```bash
docker compose exec -it opencode-worker opencode providers login
```

That worker is the current AI text-processing path used by `TG Dog Digest`.

Then build the first workflow.

## 7) Build the first workflow

Simple path:

1. Create a workflow in `n8n`.
2. Add `Manual Trigger`.
3. Add `TG Dog Source Selector`.
4. Add `TG Dog Message Reader`.
5. Optionally add `TG Dog OCR`.
6. Add `TG Dog Messages Cleanup`.
7. Add `TG Dog Digest` and/or `TG Dog Post Message`.

Useful variations:

- turn off `TG Dog Message Reader -> Include Media` for faster text-only reads
- use `TG Dog Random Message` if you want one random real message from a selected dialog
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

## Security notes

- Do not commit `.env`, `telegram_sessions`, `run_artifacts`, or exported Docker volume data.
- `app` and `api` are privileged runtime containers because they mount `/var/run/docker.sock`.
- Telegram session state and worker auth are meant to stay in Docker volumes, not in tracked files.

## Reset all data

To wipe the full local stack state and start from scratch:

```bash
make reset-data
```

That removes containers plus all named Docker volumes for Postgres, `n8n`, Telegram sessions, run artifacts, and worker auth.
