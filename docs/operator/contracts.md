# Operator Contract Map

## Common Envelope

All adapters return `services/shared/contracts/common.py::AdapterEnvelope`.

Required fields:

- `contract_version`
- `node_name`
- `run_id`
- `status`
- `payload_inline` or `payload_ref`
- `warnings`
- `metrics`
- `error` when `status=error`

## Core Contracts

- `services/shared/contracts/auth.py`: auth requests/responses and account states.
- `services/shared/contracts/run.py`: canonical run manifest.
- `services/shared/contracts/message.py`: canonical message schema.
- `services/shared/contracts/ocr.py`: OCR output records.
- `services/shared/contracts/heuristic.py`: heuristic decision output.
- `services/shared/contracts/classification.py`: classification output and provider attempts.
- `services/shared/contracts/digest.py`: digest sections and delivery chunks.
- `services/shared/contracts/delivery.py`: delivery receipt output.

## n8n node contract direction

- `n8n` custom nodes should exchange canonical message-shaped items whenever they operate on Telegram content.
- Upstream nodes may differ in transport, but downstream OCR/filter/digest logic should depend on the canonical message schema instead of raw Telegram Bot API payloads.
- Core rework path is `Telethon`-first; built-in Telegram bot nodes are optional adapters, not the canonical source contract.

## Artifact Reference Rules

- Large payloads are stored as files in `run_artifacts` and passed by path.
- `manifest.json` keeps `previous_outputs` map from `node_name` to artifact path.
- Nodes append their own artifact refs and must not mutate previous artifacts.

## OCR Provider Notes

- V1 default OCR provider is `local:tesseract`.
- Local OCR baseline expects `eng`, `ukr`, and `rus` language packs.

## Classification and Heuristic Notes

- Heuristic output is produced by `heuristic-filter` and can drop (`blacklist`) or route (`whitelist`) items.
- Classification uses ordered provider queue with first-success semantics.
- Preset provider profiles include `opencode_cli`.
- Digest sections are always rendered in order: `main`, `filtered`, `unclassified`.
- API/n8n digest output now carries canonical delivery-ready bot payload fields: `digest_text`, `parse_mode = markdown_v2`, and ordered `delivery_chunks` that must not be re-split downstream.
