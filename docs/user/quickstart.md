# Quickstart

TG-Dog is the project name used in the docs and `n8n` node picker.

## 1) Prepare environment

```bash
cp .env.example .env
```

Replace every placeholder secret before first boot. Do not keep the example password or master key values.

Set at least:

- `POSTGRES_PASSWORD`
- `N8N_PASSWORD`
- `APP_MASTER_KEY`

Optional:

- `TELEGRAM_BOT_TOKEN` if you want `TG Dog Post Message -> Sender = Bot`
- `WEBHOOK_URL` if you want public `n8n` webhooks; `TG Dog Bot Command Trigger` does not use this value directly
- `TELEGRAM_BOT_WEBHOOK_BASE_URL` as an optional stable default for `TG Dog Bot Command Trigger`; this must be the public HTTPS base URL of the `api` service, not the `n8n` editor URL

For stable interactive onboarding with `docker compose up`, also keep:

- `COMPOSE_MENU=false`

Default bootstrap owner:

- email: `admin@example.com`
- password: `N8N_PASSWORD`

## 2) Start the stack

```bash
make up
```

`make up` runs `docker compose up -d --build --wait` and then attaches an interactive onboarding session with `docker compose exec -it app python -m services.onboarding.ensure_connected`.

## 3) Open n8n

- URL: `http://localhost:50000`
- Login: `admin@example.com` / `N8N_PASSWORD` from `.env`
- The owner account is bootstrapped automatically on startup.

## 4) Confirm the workspace is ready

- The stack no longer preloads repo-managed workflows.
- New workflows you create in the UI are stored by `n8n` and should survive restart.
- Start by clicking `New Workflow`.

## 5) Connect Telegram account

Follow:

- `docs/user/telegram-app-setup.md`
- `docs/user/connect-account.md`

## 6) Run first digest

- Before using `TG Dog Digest`, log in to the OpenCode worker provider once:

```bash
docker compose exec -it opencode-worker opencode providers login
```

- Follow the interactive flow and choose the provider you want OpenCode to use.
- Provider credentials are stored in the worker state volume and should survive normal container restart/recreate.
- Complete Telegram onboarding first.
- Create a workflow manually in `n8n`.
- Add `Manual Trigger`.
- Add `TG Dog Source Selector`.
- Add `TG Dog Message Reader`.
- For faster text-only fetches, turn off `TG Dog Message Reader -> Include Media`.
- Or add `TG Dog Random Message` to pick one random real message from the full history of a selected Telegram dialog, including supported GIF/media posts.
- Or use `TG Dog Message Trigger` for real-time workflows that react to new incoming messages in one selected dialog.
- Add `TG Dog OCR`.
- Add `TG Dog Messages Cleanup`.
- Add `TG Dog Digest` and/or `TG Dog Post Message`.
- If you want bot delivery, set `TELEGRAM_BOT_TOKEN` in `.env` and use `TG Dog Post Message -> Sender = Bot`.
- If you want the digest workflow itself to start from a bot command like `/run`, add `TG Dog Bot Command Trigger` as the workflow trigger.
- Set `Command` to the bot command you want, for example `/run`.
- For personal operator-only control, leave `Only Connected Account=true` and keep `Require Private Chat=true`.
- `TG Dog Bot Command Trigger` prefers the Bot API webhook through the backend when you provide a public HTTPS base URL for the `api` service.
- You can keep a stable default in `.env` via `TELEGRAM_BOT_WEBHOOK_BASE_URL=https://<public-host>`.
- `.env` remains the default source of truth for bot-command ingress.
- Use `POST /telegram-bot-commands/config` only when you need a temporary runtime override, for example `{ "webhook_base_url": "https://<public-host>", "ingress_mode": "webhook" }`.
- To return control back to `.env`, call `POST /telegram-bot-commands/config` with `{ "use_env": true }`.
- If you explicitly switch the runtime override to polling mode, the backend falls back to real Telegram Bot API long polling for bot commands instead of relying on a public tunnel.
- When webhook mode is enabled, the effective Telegram webhook target is `https://<public-host>/telegram-bot-commands/webhook`.
- `TG Dog Message Trigger` stays on the internal webhook base URL, so user-account realtime flows like `Auto answer` do not need the public tunnel.
- Execute the workflow to verify live dialog access, recent message reads, image OCR, cleanup, and posting/digest output.

For the node-by-node workflow walkthrough, see `docs/user/run-workflow-in-n8n.md`.

## Security notes

- Do not commit `.env`, `telegram_sessions`, `run_artifacts`, or exported Docker volume data.
- `app` and `api` are privileged runtime containers because they mount `/var/run/docker.sock`.
- Telegram session state and provider auth are designed to stay in Docker volumes, not in tracked files.

You can change the owner email/password later inside n8n after first login.
