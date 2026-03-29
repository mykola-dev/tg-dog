# AGENTS.md
Rules for coding agents in TG-Dog.
Goal: follow current runtime reality, not stale plans.

## Priority
Use sources in this order: 1) direct user request, 2) system/developer instructions, 3) this file, 4) current runtime code in `api/`, `services/`, `n8n/custom-nodes/`, `docker/`, 5) current tests, 6) current docs in `docs/operator/`, `docs/user/`.

If code and docs disagree, trust code plus active tests.

## What This Repo Is
TG-Dog is a Dockerized Telegram digest system. `n8n` is the user-facing workflow editor/runtime. User-created `n8n` workflows are the persistent unit of behavior. Telegram onboarding/fetch/post use real `Telethon`. OCR uses real local `tesseract`. Digest/scoring providers run real CLI commands in worker containers.

## Required Reality Check
For tasks touching core integrations, publish a short matrix: `component -> real | legacy | placeholder | test-only -> why`. Use it for Telegram auth/fetch/post, OCR, digest, scoring, scheduling when relevant. Stop and ask if your change would make any default runtime path simulated or placeholder.

## Non-Negotiables
Keep real integrations by default; no silent simulation fallback; no repo-managed workflow import/reconcile on startup; no user-facing design that requires code editing inside `n8n`; preserve user-owned workflow persistence; preserve canonical message contracts; preserve thin `n8n -> api` bridge design; do not claim completion without fresh evidence.

## First Files To Read
Start with `docs/operator/rework-architecture.md`, `docs/operator/architecture.md`, `docs/operator/contracts.md`, `docs/operator/runbooks.md`, `docs/user/quickstart.md`, `docker-compose.yml`, `api/main.py`, `api/routers/`, `api/telegram_trigger_runtime.py`, `services/shared/config.py`, `services/shared/telegram/client.py`, `services/shared/providers/`, `n8n/custom-nodes/`.

## Runtime Topology
Main containers: `postgres`, `app`, `api`, `n8n`, `opencode-worker`.

Meaning that matters:
- `api`: FastAPI bridge for custom nodes; starts migrations plus Telegram trigger runtimes.
- `n8n`: workflow editor/runtime; stores workflows/executions in `n8n_data`; loads local custom nodes; bootstraps owner account only.
- `app`: onboarding/shared helper; starts onboarding then sleeps.
- workers: provider CLIs called with `docker exec`; auth/state stays isolated.

Persistent volumes that matter: `telegram_sessions` for Telethon auth/session state, `run_artifacts` for manifests and node outputs, `n8n_data` for workflow definitions/executions/owner state.

## Workflow Ownership
User-created workflows in `n8n` are the source of truth. Do not reintroduce repo-managed workflow imports, do not overwrite user workflows from bootstrap scripts, do not assume repo workflow files are live runtime truth, and prefer user-facing composition in `n8n` over hardcoded orchestration. `docker/n8n/workflows/` is historical unless a task explicitly revives it.

## n8n Rules
Prefer standard `n8n` nodes first. Use thin custom nodes only for Telegram user-account behavior or repo-specific bridging. Keep config in node parameters. Keep bridge `n8n -> api` over internal HTTP. Do not give `n8n` Docker socket access. Do not embed Telethon logic directly in custom nodes.

Current custom nodes: `TG Dog Source Selector`, `TG Dog Message Reader`, `TG Dog Message Trigger`, `TG Dog Random Message`, `TG Dog OCR`, `TG Dog Messages Cleanup`, `TG Dog Digest`, `TG Dog Post Message`.

Do not casually rename node types, parameter names, or response shapes.

Important env vars: `TELEGRAM_SOURCE_SELECTOR_API_URL`, `N8N_INTERNAL_WEBHOOK_BASE_URL`, `WEBHOOK_URL`.
Important bridge endpoints: `GET /dialogs`, `GET /dialogs/send-targets`, `POST /messages/read`, `POST /messages/random`, `POST /ocr/messages`, `POST /messages/cleanup`, `POST /digest/messages`, `POST /post/message`, `POST /telegram-trigger/subscribe`, `POST /telegram-trigger/unsubscribe`.

## Telegram Rules
Auth must stay real `Telethon`; preserve interactive first run in `app`, detached fallback to `make onboard`, restart reuse of stored credentials, explicit disconnect/reset, and no storage of login codes or 2FA secrets. Key files: `services/auth/main.py`, `services/onboarding/wizard.py`, `services/onboarding/startup.py`, `services/shared/telegram/client.py`.

Fetch must stay `Telethon`-backed through `TelegramClientWrapper`; preserve real dialog/history reads, no secret chats, no bot dialogs in source selection, media downloads into run workspace, image attachments as OCR candidates, and one canonical output item per message. Never generate fake Telegram messages in production paths.

Post has two real modes: user mode via `Telethon` user-session sending, bot mode via Telegram Bot API in `services/shared/telegram/bot_client.py`. Bot mode requires `TELEGRAM_BOT_TOKEN`. Do not blur modes; if posting changes, verify both.

Realtime trigger uses `api/routers/telegram_trigger.py`, `api/telegram_trigger_runtime.py`, and the trigger node. Preserve subscription persistence in Postgres, reload on API startup, real `Telethon` new-message listening, canonical message mapping, internal webhook normalization, and dialog scoping. This is not a bot-update runtime.

## OCR / Scoring / Digest
OCR: local OCR is real, remote OCR is placeholder, API route supports only local OCR. Preserve image-only behavior, `ocr_status`, and per-item failures. Key files: `services/shared/providers/ocr.py`, `api/routers/ocr.py`, `services/shared/ocr_enrichment.py`.

Scoring: worker command execution is real, provider queue/fallback is real, score interpretation is still simplified/local. Key files: `services/scoring/main.py`, `services/shared/providers/scoring.py`, `services/shared/runtime/worker_exec.py`. Do not present current scoring as full semantic LLM classification unless you wire and verify it.

Digest: current API/`n8n` path is worker-backed via `api/routers/digest_llm.py` and `services/shared/providers/digest.py`. OpenCode prompts go on stdin in the provider path; do not casually move them to argv.

## Worker Execution
Core provider execution relies on Docker socket access in `app` and `api`, stable worker container names, provider-specific persisted volumes, and timeout behavior. If touching worker execution, inspect `services/shared/runtime/worker_exec.py` and `docker-compose.yml`. Do not bypass worker containers for core provider execution unless the user explicitly wants new architecture.

## Canonical Contracts
Canonical message items are central. Sources: `docs/operator/rework-architecture.md`, `docs/operator/contracts.md`, `api/schemas.py`, `services/shared/contracts/message.py`. Preserve these invariants: one item = one message; stable source/message metadata; media stays attached to its message item; OCR enrichment stays on the same item; downstream nodes should not need a join to reconnect OCR output. Do not casually rename schema fields or reshape canonical messages into Telegram Bot API payloads.

CLI adapters share a common envelope in `services/shared/contracts/common.py`; important fields are `contract_version`, `node_name`, `run_id`, `status`, `payload_inline`/`payload_ref`, `warnings`, `metrics`, `error`.

## Artifact Rules
Large payloads move by file reference, not giant inline blobs. Store them in `run_artifacts`, track them from `manifest.json`, append outputs instead of mutating previous artifacts, and preserve previous output refs for downstream steps. If changing artifact behavior, inspect `services/shared/runtime/manifest.py` and `services/shared/runtime/artifacts.py`.

## Timezone / Filtering / Delivery
Timezone matters for scheduling/windows/retention. Relevant settings: `APP_TIMEZONE`, `GENERIC_TIMEZONE`, `TZ`. Current truths: `services/shared/config.py` validates `APP_TIMEZONE`, `n8n` receives timezone env vars from compose, many timestamps are stored in UTC.

Filtering rules: local heuristic filtering exists; blacklist beats whitelist on conflict; scoring failure degrades to `Unclassified`.

`TG Dog Messages Cleanup` is a compatibility boundary for digest/posting text. If touching cleanup or formatting, verify direct posting and digest still work.

Delivery protections that should survive: dedup by digest fingerprint, bounded chunk counts, retry handling, partial progress tracking, cooldown on repeated failures, self-loop prevention when target equals source.

## Onboarding / Bootstrap
Key commands: `make up`, `make onboard`, `make disconnect`, `docker compose exec -it app python -m services.onboarding.ensure_connected`.

Preserve interactive first-run login, detached first-run hint to run `make onboard`, and restart reuse of stored auth.

`n8n` bootstraps only the owner account. Current default owner: `admin@example.com` / `N8N_PASSWORD`. If touching bootstrap, inspect `docker/n8n/bootstrap.sh`, `docker/n8n/reseed_owner_if_needed.sh`, and `tests/integration/test_n8n_bootstrap_runtime.py`.

## Security
Treat the repo as containing real secrets/auth state. Do not print, copy, or commit `.env`, `.creds`, `telegram_sessions`, worker auth volumes, provider auth state, or runtime artifacts unless the task explicitly needs a fixture. Be careful with logs/screenshots that may reveal phone numbers, API IDs, API hashes, session identifiers, bot tokens, or worker auth state. `app` and `api` are high-trust because they have Docker socket access; do not casually expand that trust boundary.

## Docs Reality
Likely stale docs: `README.md` may understate current custom nodes; some user docs may still reference `.env.example` where `.env` is the real flow. Prefer code over prose when docs conflict.

## Verification
Evidence beats assertion. Strongest evidence: live source inspection, integration tests, e2e compose tests, explicit runtime commands. There are useful tests under `tests/integration/` and `tests/e2e/`; inspect them when relevant instead of memorizing a huge list.

For core integrations, verify at least one real path: Telegram auth/dialogs/message read/delivery; OCR via `tesseract --version`, real OCR route/CLI, or explicit real-path failure; scoring via real worker exec or explicit auth/runtime error; digest via real worker exec or explicit auth/runtime error.

Do not mark integration-heavy work done unless the real runtime path is still default, relevant commands/tests were run, outcomes are reported accurately, and remaining placeholders are listed explicitly.

Do not present these as complete without approval: `simulate_*` runtime behavior outside tests, fake providers in production paths, placeholder Telegram messages, placeholder remote OCR as real OCR, local digest rendering as worker-backed LLM digest, heuristic score synthesis as fully real provider scoring. Test-mode branches are acceptable only when clearly gated to tests.

## DB / Docs / Git Hygiene
API starts migrations on startup. If changing DB-backed runtime behavior, inspect migrations plus affected models in `api/models.py` and `services/shared/db/models.py`.

If runtime behavior changes materially, update relevant docs in the same task unless the user explicitly wants code-only work.

Useful wording in this repo: `n8n path is real`; `worker command execution is real, score semantics remain simplified`.

Do not rely on generated clutter like `.pytest_runtime/`, run outputs, or local auth state.

Git rules: do not run `git config` to fix identity; use one-off author only if commit is required and identity is missing; do not amend unless user explicitly requests it; do not use destructive git commands without explicit approval.

Before finalizing a commit-oriented task, include: 1) what is real now, 2) what is still legacy/placeholder, 3) verification commands run, 4) test results summary, 5) docs updated or intentionally left stale.

## Useful Commands
Useful current commands: `make up`, `make down`, `make restart`, `make logs`, `make test`, `make migrate`, `make onboard`, `make disconnect`, `docker compose exec -it opencode-worker opencode providers login`.

Prefer the current `.env`-based flow over stale `.env.example` examples.

## Heuristics
User workflows -> think `n8n` first. Telegram runtime -> think `Telethon` first. OCR -> think local `tesseract` first. Digest/scoring provider execution -> think worker containers first.

Do not reintroduce without explicit approval: repo-managed workflow import on startup, fake Telegram runtime paths, silent simulation flags in default runtime, direct Docker control from `n8n`, superseded custom scheduler architecture, remote OCR marketed as available when still placeholder.

Try to preserve during refactors: first-run onboarding, owner bootstrap, custom node loading, workflow persistence across restart, selector persistence, canonical message output from reader, OCR enrichment in place, digest worker execution, both sender modes in `TG Dog Post Message`, trigger subscription persistence.

## Final Reminder
TG-Dog already contains real integrations, some stale docs, and strong tests. A good agent here reads the current runtime first, preserves real paths by default, and is honest about remaining mismatches.
