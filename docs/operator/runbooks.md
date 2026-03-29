# Operator Runbooks

## Delivery failures

### Retryable failures

- Delivery retries up to 3 attempts with bounded backoff.
- If all attempts fail, receipt status is `failed` with `retry_attempts=3`.

### Cooldown and pause

- Repeated identical failures enter cooldown protection.
- Receipt status becomes `blocked_safety_policy` with `system_status=delivery paused`.

### Resume after partial delivery

- If a delivery fails after sending some chunks, progress is stored.
- Re-run delivery with resume mode to send only remaining chunks.

## Dedup behavior

- Completed digest fingerprints are recorded.
- Re-delivery attempt with same fingerprint is marked `skipped_duplicate`.

## Classification workers

### Bootstrap and health checks

- One-time logins:
  - `docker compose --env-file .env exec opencode-worker opencode providers login`
- OpenCode stores provider auth/config in the `opencode_state` volume via `XDG_CONFIG_HOME=/workspace/opencode/.config` and `XDG_DATA_HOME=/workspace/opencode/.local/share`.
- Health checks:
  - `docker compose --env-file .env exec opencode-worker opencode --version`

### Recovery

- If provider attempts show `PROVIDER_AUTH_REQUIRED`, repeat worker login commands.
- If the worker is missing or stopped, restart with `docker compose --env-file .env up -d opencode-worker`.
- If classification cannot invoke workers, verify `/var/run/docker.sock` is mounted into `app`.

## Security boundaries

- `app` and `api` mount `/var/run/docker.sock`; treat both containers as high-trust and do not expose them casually.
- Do not publish `telegram_sessions`, `run_artifacts`, `n8n_data`, `postgres_data`, or `opencode_state`.
- Do not copy session files, provider auth state, or runtime artifacts into git-tracked paths.

## n8n runtime operations

### Verify owner bootstrap

- Check `n8n` settings: `curl http://localhost:50000/rest/settings`
- Confirm `showSetupOnFirstLoad` is `false`
- If owner bootstrap fails, inspect `docker compose logs n8n`

### Verify workflow persistence

- Create a workflow in the `n8n` UI
- Restart `n8n`: `docker compose up -d --build n8n`
- Confirm the workflow is still present after restart

### Verify custom node loading

- Rebuild `n8n`: `docker compose up -d --build n8n`
- Log into `n8n`
- Search for `TG Dog Source Selector`
- If the node is missing, inspect `docker compose logs n8n` and verify `./n8n/custom-nodes:/custom-extensions:ro` is still mounted
