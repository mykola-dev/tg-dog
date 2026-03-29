# Operator Architecture

Project name: `tg-dog`.

## Runtime Topology

- `postgres` stores relational state for the backend and `n8n`.
- `api` is the FastAPI bridge for custom nodes and Telegram runtimes.
- `n8n` is the user-facing workflow editor, scheduler, and long-lived execution runtime.
- `app` handles onboarding and shared helper commands.
- `opencode-worker` runs the OpenCode CLI with isolated persisted auth state.

Current compose stack lives in `docker-compose.yml` and uses the compose project name `tg-dog`.

## What Runs Where

- `api`
  - runs DB migrations on startup
  - exposes bridge endpoints used by `n8n` custom nodes
  - loads Telegram realtime trigger subscriptions from Postgres
  - loads Telegram bot-command subscriptions/config from Postgres
  - starts the Telethon-based message trigger runtime
  - refreshes Bot API webhook or polling mode for bot-command ingress

- `n8n`
  - stores workflows and executions in `tg-dog_n8n_data`
  - bootstraps only the initial owner account
  - loads local custom nodes from `./n8n/custom-nodes`
  - is the source of truth for user-created workflows

- `app`
  - runs first-time onboarding and helper commands
  - reuses the same shared Python runtime as the backend services

- `opencode-worker`
  - stays idle until `api` or `app` runs provider commands through `docker exec`
  - stores OpenCode auth/state in `tg-dog_opencode_state`

## Persistent Volumes

- `tg-dog_postgres_data`
- `tg-dog_n8n_data`
- `tg-dog_telegram_sessions`
- `tg-dog_run_artifacts`
- `tg-dog_opencode_state`

## Real Integration Matrix

- Telegram auth / dialogs / reads / user delivery -> real -> `Telethon` via `services/shared/telegram/client.py`
- Telegram user-message trigger -> real -> `api/telegram_trigger_runtime.py` listens with `Telethon`
- Telegram bot-command ingress -> real -> Bot API webhook or polling in `api/telegram_bot_command_runtime.py`
- Bot-mode delivery -> real -> Telegram Bot API via `services/shared/telegram/bot_client.py`
- OCR -> real local | placeholder remote -> only local `tesseract` path is implemented
- AI text step -> real -> `api/routers/digest_llm.py` calls `opencode-worker`
- heuristic / classification path -> legacy or secondary -> code exists under `services/`, but it is not the main current `n8n` UX

## Custom Nodes In Current Runtime

- `TG Dog Source Selector`
- `TG Dog Message Reader`
- `TG Dog Message Trigger`
- `TG Dog Bot Command Trigger`
- `TG Dog Random Message`
- `TG Dog OCR`
- `TG Dog Messages Cleanup`
- `TG Dog Digest`
- `TG Dog Post Message`

## Workflow Ownership

- User-created workflows in `n8n` are the source of truth.
- The stack does not import or reconcile repo-managed workflows on startup.
- Restart must not overwrite user workflows.
- `docker/n8n/workflows/` is not runtime truth.

## Security Notes

- `app` and `api` mount `/var/run/docker.sock`; treat both as high-trust containers.
- `n8n` talks to `api` over internal HTTP and does not need Docker socket access.
- `telegram_sessions`, `run_artifacts`, `n8n_data`, `postgres_data`, and `opencode_state` should be treated as sensitive runtime data.
- `docker compose config` prints interpolated secrets from `.env` and should be treated as secret-bearing output.
