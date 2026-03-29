# Troubleshooting

## Auth issues

- `AUTH_CONFIG_ERROR`: verify `APP_MASTER_KEY` is set.
- `AUTH_FLOW_EXPIRED`: restart login flow and re-enter code.
- `reauth_required`: reconnect account using onboarding workflow.
- n8n login uses `admin@example.com` and `N8N_PASSWORD` from `.env`.
- If n8n shows first-run setup instead of login, restart `n8n` so its in-container bootstrap runs again: `docker compose up -d --build n8n`.
- If the owner bootstrap fails, check `docker compose logs n8n` for the exact validation error.

## Workflow issues

- The stack no longer imports repo-managed workflows on startup.
- If a workflow you created manually disappears after restart, inspect the `n8n_data` volume and `docker compose logs n8n`.
- If a custom node is missing after restart, rebuild `n8n`: `docker compose up -d --build n8n`.

## OCR issues

- Local OCR failures are recorded per item in `ocr.json`.
- Pipeline continues when OCR item fails.

## Filtering/classification issues

- If message disappears unexpectedly, check blacklist rules.
- If whitelist routing missing, verify `target_ref` on whitelist rules.
- If classification providers fail, messages should appear in `Unclassified`.
- `PROVIDER_AUTH_REQUIRED`: run worker login bootstrap again (`opencode providers login`).
- OpenCode worker login command: `docker compose exec -it opencode-worker opencode providers login`
- `BOT_TOKEN_NOT_CONFIGURED`: set `TELEGRAM_BOT_TOKEN` in `.env`, then restart `api` and `app`.
- `BOT_DELIVERY_FAILED`: Telegram Bot API rejected the target. Common causes are missing bot membership or missing admin/post rights in the selected chat or channel.
- Worker down: `docker compose up -d opencode-worker`.
- Docker socket errors from app: check `/var/run/docker.sock` mount exists for `app` in `docker-compose.yml`.

## Delivery issues

- If digest is too long, output truncates after 5 chunks with notice.
- Ensure delivery target is not selected as source.
- `failed` with retries: transient delivery issue, system already retried 3 times.
- `blocked_safety_policy` / `delivery paused`: repeated identical failures; wait and re-run later.
- `skipped_duplicate`: identical digest already delivered.
