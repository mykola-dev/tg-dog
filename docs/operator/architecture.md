# Operator Architecture

Project name: `TG-Dog`.

## Deployment Topology

- `postgres` container stores relational state.
- `n8n` container is the user-facing control plane and scheduler.
- `n8n` bootstraps the initial owner account during startup and persists user-created workflows in `n8n_data`.
- `app` container runs local adapter CLIs and shared runtime code.
- `opencode-worker` container runs OpenCode CLI with isolated auth state.
- `app` executes classification commands in workers through Docker socket (`docker exec`).
- `n8n` calls the `api` container over internal HTTP bridge endpoints from workflows (for example `http://api:8000/...`).

Current design reference: `docs/operator/rework-architecture.md`.

## Persistent Volumes

- `postgres_data`: relational database files.
- `n8n_data`: workflow and execution metadata.
- `telegram_sessions`: Telegram session artifacts.
- `run_artifacts`: per-run manifests, node artifacts, and logs.
- `opencode_state`: persisted OpenCode CLI auth/session state, including `XDG_CONFIG_HOME=/workspace/opencode/.config` and `XDG_DATA_HOME=/workspace/opencode/.local/share`.

## Runtime Layout

- `runs/<run_id>/manifest.json`
- `runs/<run_id>/messages.json`
- `runs/<run_id>/ocr.json`
- `runs/<run_id>/heuristic.json`
- `runs/<run_id>/classification.json`
- `runs/<run_id>/digest.json`
- `runs/<run_id>/delivery.json`
- `runs/<run_id>/logs/<node_name>.log`

## Node Responsibilities

- `auth`: account connection lifecycle.
- `fetch`: source-scoped canonical message ingestion runtime in Python services.
- `ocr`: optional OCR extraction.
- `heuristic-filter`: local whitelist/blacklist matching.
- `classification`: AI provider queue based classification.
- `digest`: final section assembly and chunking.
- `delivery`: Telegram send and receipt recording.

`n8n` custom nodes are the preferred user-facing control surface for the rework, starting with selector and message-reader nodes.

## Reliability Components

- single active-run lock
- digest fingerprint dedup store
- resume-safe partial delivery progress
- retry and cooldown protection for repeated delivery failures

## Security Notes

- Docker socket mount in `app` is privileged; treat `app` as high-trust runtime for classification-worker orchestration.
- Docker socket mount in `api` is also privileged; treat `api` as high-trust runtime for worker orchestration and Telegram bot webhook management.
- `n8n` reaches the stack through internal HTTP calls into `api`, so it does not need Docker socket access for the phase-1 bridge.
- Classification workers expose no public ports and mount only dedicated state volumes.
- Provider credentials must stay in provider-specific volumes and never in shared app env dumps.
