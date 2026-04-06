# Operator Contract Map

## Canonical Telegram Message Item

The main content-processing path uses one canonical message shape.

Primary sources:
- `api/schemas.py`
- `services/shared/contracts/message.py`

Core fields:
- `schema_version`
- `source_kind`
- `source_id`
- `source_title`
- `message_id`
- `message_timestamp`
- `author_id`
- `author_title`
- `text`
- `reply_to_message_id`
- `forwarded_from_source_id`
- `is_outbound`
- `is_from_self`
- `is_service_message`
- `media_items`
- `ingestion_meta`

Invariants:
- one item = one Telegram message
- media stays attached to that same message item
- OCR enrichment stays on that same item
- downstream nodes should not need a join step to reconnect OCR output

## Media Item Rules

Current media item fields:
- `media_kind`
- `file_ref`
- `mime_type`
- `size_bytes`
- `ocr_status`
- `ocr_text`
- `ocr_confidence_hint`
- `ocr_error_code`
- `ocr_error_message`

Current runtime truth:
- image media is the OCR input path
- supported GIF-style media can flow through random read and repost paths
- non-image OCR is not implemented

## AI Text Contract

`POST /ai/text` accepts:
- `prompt`
- `system_prompt`
- `command_template`

`POST /ai/text` returns:
- `output_text`
- `provider_id`
- `provider_attempts`
- `raw_output`

Important behavior:
- the AI endpoint executes the local OpenCode CLI through `api`
- prompt content still goes to the worker on stdin
- Telegram delivery shaping is no longer part of this endpoint contract
- chunking and delivery-ready shaping belong in workflow logic before `POST /post/message`

## Trigger Contracts

### User-message trigger

`TG Dog Message Trigger` delivers canonical Telegram message items to `n8n`.

### Bot-command trigger

`TG Dog Bot Command Trigger` uses a different trigger payload shape.

Key fields:
- `schema_version`
- `trigger_kind`
- `workflow_id`
- `node_id`
- `command`
- `command_text`
- `chat_id`
- `chat_type`
- `message_id`
- `message_timestamp`
- `user_id`
- `username`
- `first_name`
- `last_name`
- `raw_update`

Do not distort canonical Telegram message items to look like bot-command payloads, and do not distort bot-command payloads to look canonical unless you are explicitly adding a normalizer step.

## Large Payload Rules

- Large runtime payloads should move by file reference, not giant inline blobs.
- Artifact helpers under `services/shared/runtime/` are the operational truth.
- Preserve previous output refs for downstream steps instead of mutating old artifacts in place.

## Legacy Contracts Still In Repo

The repo still contains contract files for heuristic/classification and older CLI-oriented flows.

Current stance:
- they are real code paths in `services/`
- they are not the main current `n8n` product path
- do not present them as the default UX without fresh verification
