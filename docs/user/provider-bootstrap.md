# Provider Worker Bootstrap

## One-time provider login

Run these once after `docker compose up -d`:

```bash
docker compose exec opencode-worker opencode providers login
```

Sessions are stored in isolated worker volumes:

- `opencode_state` -> `/workspace/opencode`

## Verify worker state and CLI readiness

```bash
docker compose exec opencode-worker sh -lc "ls -la /workspace/opencode"
docker compose exec opencode-worker opencode --version
```

## When to re-login

Re-run login if any of these happen:

- provider returns auth-required error (`PROVIDER_AUTH_REQUIRED`)
- worker state volume was removed/replaced
- provider token/session was revoked
