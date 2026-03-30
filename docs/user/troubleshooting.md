# Troubleshooting

## Auth issues

- `AUTH_CONFIG_ERROR`: verify `APP_MASTER_KEY` is set.
- `AUTH_FLOW_EXPIRED`: restart login flow and re-enter code.
- `reauth_required`: reconnect account using onboarding workflow.
- If Telegram onboarding was skipped on detached startup, run `make connect-telegram`.
- If you need to clear the stored Telegram session and reconnect, run `make reset-telegram`.
- On a fresh `n8n_data` volume, `n8n` should show its standard first-run owner setup in the browser.
- If `n8n` does not load correctly after rebuild or restart, inspect `docker compose logs n8n`.

## Workflow issues

- The stack no longer imports repo-managed workflows on startup.
- If a workflow you created manually disappears after restart, inspect the `n8n_data` volume and `docker compose logs n8n`.
- If a custom node is missing after restart, rebuild `n8n`: `docker compose up -d --build n8n`.

## OCR issues

- Local OCR failures are recorded per item in `ocr.json`.
- Pipeline continues when OCR item fails.
- Only the local `tesseract` path is implemented in the current runtime.

## AI worker issues

- `PROVIDER_AUTH_REQUIRED`: run worker login bootstrap again (`opencode providers login`).
- OpenCode worker login command: `docker compose exec -it opencode-worker opencode providers login`
- `Digest provider command failed`: the backend could not get a valid result from the worker command
- `BOT_TOKEN_NOT_CONFIGURED`: set `TELEGRAM_BOT_TOKEN` in `.env`, then restart `api` and `app`.
- `BOT_DELIVERY_FAILED`: Telegram Bot API rejected the target. Common causes are missing bot membership or missing admin/post rights in the selected chat or channel.
- Worker down: `docker compose up -d opencode-worker`.
- Docker socket errors from worker execution: check `/var/run/docker.sock` mounts for `api` and `app` in `docker-compose.yml`.

## Legacy filtering/classification code

- The repo still contains heuristic/classification code under `services/`.
- That path is not the main current `n8n` UX.
- If you are debugging that older path specifically, verify it directly in code/tests instead of assuming the user docs describe it fully.

## Delivery issues

- If digest is too long, output truncates after 5 chunks with notice.
- Ensure delivery target is not selected as source.
- `failed` with retries: transient delivery issue, system already retried 3 times.
- `blocked_safety_policy` / `delivery paused`: repeated identical failures; wait and re-run later.
- `skipped_duplicate`: identical digest already delivered.
