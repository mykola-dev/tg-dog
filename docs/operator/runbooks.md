# Operator Runbooks

## Core Commands

- `make up`
- `make down`
- `make restart`
- `make logs`
- `make test`
- `make migrate`
- `make connect-telegram`
- `make reset-telegram`
- `make reset-data`
- `docker compose exec -it opencode-worker opencode providers login`

## First-Run Checks

### Verify stack health

- `docker compose ps`
- `http://localhost:8000/health` should return `{"status":"ok"}`
- open `http://localhost:50000`

### Verify n8n first-run setup

- on a fresh `n8n_data` volume, open `http://localhost:50000` and create the owner account in the `n8n` UI
- on subsequent runs, log in with the owner account created in the UI

### Verify Telegram onboarding

- on first `make up`, the app should start the interactive onboarding flow
- if startup was detached, run `make connect-telegram`
- if auth was broken or stale, run `make reset-telegram` and connect again

## Bot Command Runtime

### Default behavior

- if `TELEGRAM_BOT_TOKEN` is unset, bot-command ingress stays inactive
- if a public `TELEGRAM_BOT_WEBHOOK_BASE_URL` exists, runtime prefers webhook mode
- otherwise runtime falls back to Bot API polling

### Inspect effective config

- `GET /telegram-bot-commands/config`
- `POST /telegram-bot-commands/reload`

### Temporary override

- `POST /telegram-bot-commands/config` with `{"webhook_base_url":"https://<public-host>","ingress_mode":"webhook"}`
- `POST /telegram-bot-commands/config` with `{"ingress_mode":"polling"}`
- `POST /telegram-bot-commands/config` with `{"use_env":true}` to return control to `.env`

### Common failure mode

- Bot API `409 Conflict` usually means another consumer is already using `getUpdates` or the webhook/polling mode is fighting with another process.

## Worker Runtime

### One-time login

- `docker compose exec -it opencode-worker opencode providers login`

### Basic checks

- `docker compose exec opencode-worker opencode --version`
- if worker-backed AI calls fail with auth errors, repeat the login inside `opencode-worker`

### Recovery

- restart worker: `docker compose up -d opencode-worker`
- if worker execution itself fails, verify `/var/run/docker.sock` is still mounted into `api` and `app`

## Workflow Runtime Checks

### Verify workflow persistence

- create a workflow in the `n8n` UI
- restart `n8n`: `docker compose up -d --build n8n`
- confirm the workflow still exists

### Verify custom node loading

- rebuild `n8n`: `docker compose up -d --build n8n`
- log in to `n8n`
- search for `TG Dog Source Selector`
- if custom nodes are missing, inspect `docker compose logs n8n`

## Retention and Cleanup

Current runtime truth:
- implemented in `services/shared/runtime/retention.py`
- cleanup scans `runs/*/run_meta.json`
- successful runs are kept for 14 days
- failed runs are kept for 30 days
- active run is preserved when `active_run_id` is supplied

Treat `run_artifacts` as sensitive data during cleanup and debugging.

### Full local reset

- `make reset-data` removes containers and all named Docker volumes for the local stack
- use it when you need a true clean-room restart of Postgres, `n8n`, Telegram session state, run artifacts, and worker auth

## Security Boundaries

- `app` and `api` are high-trust because they mount `/var/run/docker.sock`
- do not publish `.env`, `telegram_sessions`, `run_artifacts`, `n8n_data`, `postgres_data`, or `opencode_state`
- do not casually share output from `docker compose config`, because it prints resolved secrets
