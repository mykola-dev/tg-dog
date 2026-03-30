# Operator Architecture

Project name: `tg-dog`.

## Runtime Topology

- `postgres` stores relational state for the backend and `n8n`.
- `api` is the FastAPI bridge, the main Python backend, and the runtime entrypoint for helper commands and OpenCode execution.
- `n8n` is the user-facing workflow editor, scheduler, and long-lived execution runtime.

Current compose stack lives in `docker-compose.yml` and uses the compose project name `tg-dog`.

## What Runs Where

- `api`
  - runs DB migrations on startup
  - exposes bridge endpoints used by `n8n` custom nodes
  - loads Telegram realtime trigger subscriptions from Postgres
  - loads Telegram bot-command subscriptions/config from Postgres
  - starts the Telethon-based message trigger runtime
  - refreshes Bot API webhook or polling mode for bot-command ingress
  - runs Telegram onboarding and helper CLI flows when invoked with `docker compose exec api ...`
  - runs the local OpenCode CLI with persisted auth/state

- `n8n`
  - stores workflows and executions in `tg-dog_n8n_data`
  - uses the standard `n8n` first-run owner setup on a fresh data volume
  - loads local custom nodes from `./n8n/custom-nodes`
  - is the source of truth for user-created workflows

## Persistent Volumes

- `<compose-project>_postgres_data`
- `<compose-project>_n8n_data`
- `<compose-project>_telegram_sessions`
- `<compose-project>_run_artifacts`
- `<compose-project>_opencode_state`

With the default project name, these appear as `tg-dog_*` volumes.

## Real Integration Matrix

- Telegram auth / dialogs / reads / user delivery -> real -> `Telethon` via `services/shared/telegram/client.py`
- Telegram user-message trigger -> real -> `api/telegram_trigger_runtime.py` listens with `Telethon`
- Telegram bot-command ingress -> real -> Bot API webhook or polling in `api/telegram_bot_command_runtime.py`
- Bot-mode delivery -> real -> Telegram Bot API via `services/shared/telegram/bot_client.py`
- OCR -> real local | placeholder remote -> only local `tesseract` path is implemented
- AI text step -> real -> `api/routers/digest_llm.py` runs local OpenCode CLI inside `api`
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

- `n8n` talks to `api` over internal HTTP and does not need Docker socket access.
- `telegram_sessions`, `run_artifacts`, `n8n_data`, `postgres_data`, and `opencode_state` should be treated as sensitive runtime data.
- `docker compose config` prints interpolated secrets from `.env` and should be treated as secret-bearing output.
