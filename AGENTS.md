# AGENTS.md
Rules for coding agents in TG-Dog.

Goal: follow current runtime reality, not stale plans or half-dead docs.

## Priority
Use sources in this order:
1. direct user request
2. system/developer instructions
3. this file
4. current runtime code in `docker-compose.yml`, `api/`, `services/`, `n8n/custom-nodes/`, `docker/`
5. current tests
6. current docs in `README.md`, `docs/operator/`, `docs/user/`

If code and docs disagree, trust code plus active tests.

## What This Repo Is
TG-Dog is a self-hosted Telegram automation platform built around `n8n`.

Current product truth:
- `n8n` is the user-facing workflow editor, scheduler, and long-lived runtime.
- User-created `n8n` workflows are the persistent unit of behavior.
- Telegram user-account auth, dialog listing, message reads, realtime user-message triggers, and user-mode delivery use real `Telethon`.
- Bot-command ingress and bot-mode delivery use the real Telegram Bot API when `TELEGRAM_BOT_TOKEN` is configured.
- OCR is real only through local `tesseract`.
- The current AI text step runs through `api -> /digest/messages -> local opencode CLI`.
- The node is still named `TG Dog Digest`, but in practice it is the current general AI text-processing step, not just a digest-only feature.
- Legacy heuristic/classification code still exists in `services/`, but it is not the main current `n8n` UX and should not be treated as the primary product path unless explicitly revived and verified.

## Required Reality Check
For tasks touching core integrations, publish a short matrix:
`component -> real | legacy | placeholder | test-only -> why`

Use it when relevant for:
- Telegram auth / fetch / post
- Telegram user-message trigger
- Telegram bot-command ingress
- OCR
- AI worker / digest path
- classification / heuristic paths
- retention / cleanup

Stop and ask if your change would make any default runtime path simulated, fake, or placeholder.

## Non-Negotiables
- Keep real integrations by default.
- No silent simulation fallback in production paths.
- No repo-managed workflow import/reconcile on startup.
- No user-facing design that requires code edits inside `n8n`.
- Preserve user-owned workflow persistence.
- Preserve canonical message contracts.
- Preserve the thin `n8n -> api` bridge design.
- Do not claim completion without fresh evidence.

## First Files To Read
Start with:
- `README.md`
- `docs/user/quickstart.md`
- `docs/operator/architecture.md`
- `docs/operator/contracts.md`
- `docs/operator/runbooks.md`
- `docker-compose.yml`
- `api/main.py`
- `api/routers/`
- `api/telegram_trigger_runtime.py`
- `api/telegram_bot_command_runtime.py`
- `services/shared/config.py`
- `services/shared/telegram/client.py`
- `services/shared/providers/`
- `n8n/custom-nodes/`

## Runtime Topology
Compose project name: `tg-dog`.

Main containers:
- `postgres`
- `api`
- `n8n`

Meaning that matters:
- `api`: FastAPI bridge for custom nodes; runs DB migrations on startup; loads and starts Telegram trigger runtime; loads and refreshes Telegram bot-command runtime; also serves as the main Python runtime for helper commands and OpenCode execution.
- `n8n`: workflow editor/runtime; stores workflows and executions; bootstraps only the owner account; loads local custom nodes from `./n8n/custom-nodes`.

Persistent Docker volumes that matter:
- `tg-dog_postgres_data`
- `tg-dog_n8n_data`
- `tg-dog_telegram_sessions`
- `tg-dog_run_artifacts`
- `tg-dog_opencode_state`

## Workflow Ownership
User-created workflows in `n8n` are the source of truth.

Do not reintroduce:
- repo-managed workflow imports on startup
- bootstrap scripts that overwrite user workflows
- assumptions that files in `docker/n8n/workflows/` are live runtime truth

Prefer user-facing composition in `n8n` over hardcoded orchestration.

## n8n Rules
Prefer standard `n8n` nodes first. Use custom nodes only where Telegram user-account behavior or repo-specific bridge logic is actually needed.

Current custom nodes:
- `TG Dog Source Selector`
- `TG Dog Message Reader`
- `TG Dog Message Trigger`
- `TG Dog Bot Command Trigger`
- `TG Dog Random Message`
- `TG Dog OCR`
- `TG Dog Messages Cleanup`
- `TG Dog Digest`
- `TG Dog Post Message`

Do not casually rename node types, parameter names, or response shapes.

Important env vars:
- `TELEGRAM_SOURCE_SELECTOR_API_URL`
- `N8N_INTERNAL_WEBHOOK_BASE_URL`
- `WEBHOOK_URL`
- `TELEGRAM_BOT_WEBHOOK_BASE_URL`
- `TELEGRAM_BOT_TOKEN`

Important bridge endpoints:
- `GET /dialogs`
- `GET /dialogs/send-targets`
- `POST /messages/read`
- `POST /messages/random`
- `POST /messages/cleanup`
- `POST /ocr/messages`
- `POST /digest/messages`
- `POST /post/message`
- `POST /telegram-trigger/subscribe`
- `POST /telegram-trigger/unsubscribe`
- `GET /telegram-bot-commands/config`
- `POST /telegram-bot-commands/config`
- `POST /telegram-bot-commands/subscribe`
- `POST /telegram-bot-commands/unsubscribe`
- `POST /telegram-bot-commands/reload`
- `POST /telegram-bot-commands/webhook`

## Telegram Rules
Auth must stay real `Telethon`.

Preserve:
- interactive first run through `api`
- detached fallback to `make connect-telegram`
- restart reuse of stored credentials
- explicit disconnect/reset flow
- no storage of login codes or 2FA secrets

Important auth details:
- `api_hash` is persisted in `telegram_sessions/auth_state.json`
- newly stored `api_hash` values are encrypted with `APP_MASTER_KEY`
- legacy `enc:` values still exist as backward-compatible read path

Fetch must stay `Telethon`-backed through `TelegramClientWrapper`.

Preserve:
- real dialog/history reads
- no secret chats in the selector path
- no bot dialogs in source selection
- media downloads into run workspace
- image attachments as OCR candidates
- one canonical output item per message

Never generate fake Telegram messages in production paths.

Realtime user-message trigger uses:
- `api/routers/telegram_trigger.py`
- `api/telegram_trigger_runtime.py`
- `TG Dog Message Trigger`

Preserve:
- subscription persistence in Postgres
- reload on API startup
- real `Telethon` new-message listening
- dialog scoping
- canonical message mapping
- internal webhook normalization through `N8N_INTERNAL_WEBHOOK_BASE_URL`

This is not a bot-update runtime.

Telegram bot-command ingress is a separate runtime using the Bot API.

Preserve:
- subscription persistence in Postgres
- webhook mode when an effective public API base URL exists
- polling mode fallback when no webhook base URL is available or DB override forces polling
- runtime override through `POST /telegram-bot-commands/config`
- secret-token validation on webhook mode
- separation between bot-command ingress and `Telethon` user-account ingress

Post has two real modes:
- user mode via `Telethon`
- bot mode via Telegram Bot API in `services/shared/telegram/bot_client.py`

Bot mode requires `TELEGRAM_BOT_TOKEN`. Do not blur the two delivery paths.

## OCR, AI Worker, and Legacy Classification
OCR:
- local OCR is real
- remote OCR is placeholder / not implemented runtime
- API route supports only local OCR
- OCR is image-only; non-image media is skipped
- important files: `services/shared/providers/ocr.py`, `services/shared/ocr_enrichment.py`, `api/routers/ocr.py`

AI text step:
- current `n8n` path is API-local via `api/routers/digest_llm.py` and `services/shared/providers/digest.py`
- `TG Dog Digest` is the current node name, but the path is effectively the general AI text-processing worker path
- prompts go to the worker on stdin; do not casually move them to argv
- digest delivery shaping also happens here: `digest_text`, `parse_mode`, and pre-split `delivery_chunks`

Legacy heuristic/classification path:
- code still exists in `services/heuristic_filter/`, `services/classification/`, and `services/shared/providers/classification.py`
- worker execution there is real, but score semantics are still simplified/local
- treat this as legacy or secondary unless the user explicitly wants to revive and verify it in the current `n8n` UX
- do not market it as the main current product path by accident

## Worker Execution
Core provider execution relies on:
- persisted worker auth in `tg-dog_opencode_state`
- local OpenCode CLI execution inside `api`
- timeout handling in `services/shared/runtime/worker_exec.py`

Do not bypass the real local OpenCode CLI execution path for core provider execution unless the user explicitly wants a different architecture.

## Canonical Contracts
Canonical message items are central. Inspect:
- `api/schemas.py`
- `services/shared/contracts/message.py`
- `docs/operator/contracts.md`

Preserve these invariants:
- one item = one message
- stable source/message metadata
- media stays attached to its message item
- OCR enrichment stays on the same item
- downstream nodes should not need a join to reconnect OCR output

Do not casually reshape canonical messages into Telegram Bot API payloads.

Also relevant:
- cleanup responses carry `combined_text` and/or `formatted_messages`
- AI text responses carry `digest_text`, `parse_mode`, `delivery_chunks`, `provider_attempts`, and `raw_output`
- bot-command trigger payloads are their own trigger schema and should stay separate from canonical Telegram message items

## Artifact and Retention Rules
Large payloads move by file reference, not giant inline blobs.

Store them in `run_artifacts`, track them from the manifest/artifact helpers, and preserve previous output refs for downstream steps.

Retention reality now:
- implemented in `services/shared/runtime/retention.py`
- scans `runs/*/run_meta.json`
- keeps successful runs for 14 days
- keeps failed runs for 30 days
- never removes the active run when `active_run_id` is supplied

## Onboarding and Bootstrap
Important commands:
- `make up`
- `make down`
- `make restart`
- `make logs`
- `make test`
- `make migrate`
- `make connect-telegram`
- `make reset-telegram`
- `make login-opencode`
- `make reset-data`

Current runtime behavior:
- `make up` runs `docker compose up -d --build --wait` and then starts interactive onboarding in `api`
- first-time detached startup prints a hint to run `make connect-telegram`
- `n8n` uses its standard first-run owner setup on a fresh data volume

## Security
Treat the repo as containing real secrets and auth state.

Do not print, copy, or commit:
- `.env`
- `telegram_sessions`
- worker auth volumes
- provider auth state
- runtime artifacts

Be careful with logs, screenshots, and copied command output.

Important footgun:
- `docker compose config` prints interpolated secrets from `.env`


## Docs Reality
Prefer code over docs when they disagree.

Current docs policy:
- keep docs small and current
- update docs in the same task when runtime behavior materially changes, unless the user explicitly wants code-only work
- delete stale speculative docs instead of preserving a misleading doc graveyard

## Verification
Evidence beats assertion.

Strong evidence:
- current source inspection
- integration tests
- e2e compose tests
- explicit runtime commands

For integration-heavy tasks, report:
1. what is real now
2. what is still legacy or placeholder
3. commands/tests run
4. outcomes
5. docs updated, simplified, or removed

For core integrations, verify at least one real path when touched:
- Telegram auth/dialogs/read/delivery
- user-message trigger and/or bot-command ingress
- OCR via real `tesseract` path or explicit real-path failure
- AI worker exec via real worker command or explicit auth/runtime error

## Git and Cleanup Hygiene
- Do not run destructive git commands without explicit approval.
- Do not amend commits unless explicitly requested.
- Do not rely on generated clutter like `.pytest_runtime/`, local run outputs, or local auth state.

## Final Reminder
TG-Dog already has a real `n8n` path, real Telegram integrations, a real OCR path, and a real worker-backed AI text step. Good work here means reading the current runtime first, preserving those real paths, and being honest about what is still legacy or placeholder.
