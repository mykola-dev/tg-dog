# Retention and Cleanup

## Default retention policy

- Successful run artifacts: 14 days
- Failed run artifacts: 30 days
- Media and OCR intermediates currently follow the same run-directory retention unless explicitly cleaned earlier.

## Cleanup behavior

- Artifact cleanup is a backend runtime function, not a repo-managed `n8n` workflow.
- Active run artifacts are never removed.
- Runtime cleanup scans `runs/*/run_meta.json` and removes expired run directories.

## Operational notes

- Keep backups for `postgres_data`, `telegram_sessions`, and `run_artifacts`.
- Verify system clock and timezone before troubleshooting retention behavior.
- Treat runtime volumes and artifacts as sensitive operational data; they are not safe sample data for a public repo.
