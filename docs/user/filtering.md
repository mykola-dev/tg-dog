# Filtering and Classification

The current rework path is: selector -> message reader -> OCR -> filter -> cleanup -> digest/post.

Filtering and classification nodes should consume canonical message-shaped items rather than raw Telegram payloads.

## Heuristic filter (local, fast)

Heuristic filtering runs locally and supports `en`, `uk`, `ru` token normalization.

Rule kinds:

- `blacklist`: drop matched messages from user-facing digest output.
- `whitelist`: copy matched messages into target-specific whitelist buckets.

Conflict rule:

- If a message matches both whitelist and blacklist, blacklist wins.

## AI classification

Classification is configured as ordered provider queue.

- Providers run in order.
- First valid provider result stops the queue.
- If all providers fail, classification is degraded and item goes to `Unclassified`.
- `opencode_cli` executes in a dedicated worker container (`opencode-worker`) instead of inside `app`.
- Worker auth is manual one-time bootstrap; see `docs/user/provider-bootstrap.md`.

Classification rule fields:

- `name`
- `mode` (`suppress_topic` or `boost_topic`)
- `prompt_text`
- `threshold` (0-100)
- `enabled`

## Provider presets

V1 includes command-profile preset `OpenCode CLI`.

Priority is not hardcoded; user controls queue order.

## Privacy notes

- Local heuristic filtering is fully on-host.
- Classification provider behavior depends on provider config.
- If provider can send text off-host, this must be explicit in setup.
