# Custom Node Reduction Plan

## Purpose

This document defines a phased cleanup milestone for reducing TG-Dog custom n8n nodes in favor of built-in n8n nodes where the custom node is only a thin wrapper and does not carry essential Telegram bridge behavior.

This is an execution plan, not a brainstorming note.

Rules for using this plan:

- Execute exactly one phase per working session.
- Stop after each phase.
- Do not silently merge phases.
- Update docs and tests in the same phase as the runtime change.
- If a phase reveals a hidden dependency or contract mismatch, update this plan before starting the next phase.
- Preserve real runtime behavior by default. No fake Telegram paths, no fake OCR paths, no fake AI worker paths.

## Why This Milestone Exists

The project currently ships a mix of:

- custom nodes that are real Telegram bridge surfaces and still justified
- custom nodes that are mostly small wrappers around internal HTTP endpoints or local formatting logic

The cleanup goal is not "remove custom code at any cost". The goal is to remove custom nodes that no longer provide enough value to justify their maintenance cost, while keeping the bridge nodes that still represent real product-specific runtime behavior.

This plan focuses on the weak custom-node candidates first:

- `TG Dog OCR`
- `TG Dog Messages Cleanup`
- `TG Dog Digest`

It does not assume that every remaining custom node should be removed in this milestone.

## Current Runtime Reality

Priority rule for this milestone: trust the current runtime and tests over old assumptions.

Reality matrix:

| Component | Status | Why |
| --- | --- | --- |
| Telegram auth | real | Uses real Telethon auth flow and persisted session state |
| Telegram dialog listing | real | Backed by Telethon through the API bridge |
| Telegram message read path | real | Backed by Telethon and canonical message mapping |
| Telegram user-message trigger | real | Separate Telethon runtime with subscription persistence |
| Telegram bot-command ingress | real | Separate Bot API runtime with webhook and polling support |
| Telegram delivery in user mode | real | Uses Telethon send path |
| Telegram delivery in bot mode | real | Uses Telegram Bot API |
| OCR | real local | `tesseract` is installed in the `api` container |
| AI text worker | real | Uses local OpenCode CLI in `api` |
| `TG Dog OCR` node | thin wrapper | Wraps `POST /ocr/messages` |
| `TG Dog Messages Cleanup` node | thin wrapper | Wraps `POST /messages/cleanup` |
| `TG Dog Digest` node | removed target | Replaced by built-in `HTTP Request` plus built-in shaping logic |
| `TG Dog Source Selector` node | justified for now | Provides dynamic UI for real Telegram dialog selection |
| `TG Dog Message Reader` node | removed | Replaced by built-in `HTTP Request` to `POST /messages/read` |
| `TG Dog Post Message` node | justified for now | Encapsulates repo-specific delivery choices across user and bot modes |
| `TG Dog Message Trigger` node | justified for now | Encapsulates real Telethon trigger subscription behavior |
| `TG Dog Bot Command Trigger` node | justified for now | Encapsulates real bot-command ingress behavior |

## Decisions Already Made

These are not open questions for this milestone anymore.

### 1. OpenCode stays in `api`

Chosen direction:

- keep OpenCode execution in the `api` runtime
- keep OpenCode auth and state in the current persisted API-side location
- do not move OpenCode execution into the `n8n` container in this milestone

Why:

- `opencode` is installed in `api`
- persisted state already belongs to the current worker runtime
- current login flow already targets `api`
- moving the worker into `n8n` would be a separate architecture migration, not a node cleanup

Consequence:

- the replacement AI step should use built-in `HTTP Request` against the API, not built-in `Execute Command` inside `n8n` as the default path

### 2. Telegram output moves toward HTML

Chosen direction:

- stop treating MarkdownV2 as the output contract for AI-generated delivery
- move the target delivery format toward Telegram HTML

Why:

- Markdown-style delivery formatting is expensive to sanitize correctly
- it is unpleasant to maintain
- a move to HTML should simplify the output contract if implemented carefully

Consequence:

- the delivery backend must gain `html` parse mode support
- chunking logic must become HTML-safe, not just length-based
- legacy Markdown shaping code should not define the future architecture

### 3. AI replacement should be two built-in workflow steps, not three tiny ones

Chosen replacement shape:

1. one built-in node for prompt assembly plus OpenCode request
2. one built-in node for Telegram delivery shaping and chunking

This means the target built-in workflow is:

- `HTTP Request` for the OpenCode-backed AI step
- `Code` for Telegram-safe shaping into delivery chunks

The plan should not over-fragment this into fake micro-steps that make the workflow worse instead of simpler.

### 4. OCR should use API-backed HTTP, not local OCR inside `n8n`

Chosen direction:

- replace `TG Dog OCR` with built-in `HTTP Request` to `POST /ocr/messages`
- do not run local OCR directly inside `n8n` unless a later milestone explicitly changes the container runtime

Why:

- `tesseract` exists in `api`
- `n8n` does not currently ship the OCR runtime stack
- switching OCR execution into `n8n` would be a separate runtime migration

## End State For This Milestone

At the end of this milestone, the intended state is:

- `TG Dog OCR` removed
- `TG Dog Messages Cleanup` removed
- `TG Dog Digest` removed
- replacement workflow patterns documented using built-in nodes
- AI call path handled through built-in `HTTP Request` to the API
- Telegram output shaping handled through built-in `Code`
- Telegram delivery backend supports HTML as a first-class parse mode
- docs and tests updated to match the new runtime truth

The intended state is not:

- moving Telegram bridge logic into generic nodes
- moving OpenCode execution into `n8n`
- deleting Telethon-backed bridge features that still define the product

## Out Of Scope For This Milestone

The following items are explicitly out of scope unless a later plan revision says otherwise:

- removing `TG Dog Source Selector`
- removing `TG Dog Message Reader`
- removing `TG Dog Post Message`
- removing `TG Dog Message Trigger`
- removing `TG Dog Bot Command Trigger`
- changing Telegram auth architecture
- changing Telethon session storage model
- moving OCR runtime from `api` into `n8n`
- moving OpenCode runtime from `api` into `n8n`

These can be reviewed later, but they are not phase targets in this milestone.

## Phase Overview

| Phase | Name | Outcome |
| --- | --- | --- |
| 1 | Remove thin transform nodes | `TG Dog OCR` and `TG Dog Messages Cleanup` replaced with built-in flows |
| 2 | Add Telegram HTML delivery support | Backend delivery path supports `html` parse mode |
| 3 | Introduce built-in OpenCode request flow | Built-in `HTTP Request` becomes the canonical AI step |
| 4 | Remove `TG Dog Digest` and finish cleanup | Digest custom node and stale references are removed |

Each phase below is intentionally detailed and must be treated as a standalone stop point.

## Phase 1: Remove Thin Transform Nodes

### Goal

Remove the two weakest custom transform nodes first:

- `TG Dog OCR`
- `TG Dog Messages Cleanup`

Replace them with built-in n8n patterns while preserving the real backend behavior.

This phase is intentionally paired because both nodes are the same kind of maintenance burden:

- small custom wrappers
- limited UX value
- straightforward built-in replacements

### Why These Two Are Paired

They sit in the same class of problem:

- they are not Telegram bridge nodes
- they are not trigger nodes
- they are not essential dynamic-selector UI nodes
- they mostly convert input to output using existing backend logic

Removing them together creates one coherent change: "thin transform nodes are no longer first-class custom nodes".

### Scope

In scope:

- remove the custom node packages for OCR and cleanup
- remove OCR and cleanup node loading expectations from tests
- replace workflow guidance with built-in node recipes
- keep real OCR runtime behavior intact through the API
- decide whether the cleanup API endpoint remains temporarily or is also removed as dead code if no longer justified

Not in scope:

- changing OCR provider behavior
- changing canonical message schema
- changing Telegram read behavior
- changing delivery parse modes
- touching digest replacement

### Expected Runtime After This Phase

Expected user-facing workflow pattern:

- `TG Dog Message Reader`
- optional built-in `HTTP Request` to `/ocr/messages`
- built-in `Code` and/or field transform nodes for text cleanup and formatting
- later AI or delivery steps unchanged

Expected backend reality after this phase:

- OCR still runs in `api`
- canonical message contracts remain intact
- no custom OCR node in `n8n`
- no custom cleanup node in `n8n`

### Files Likely Touched

Expected code areas:

- `n8n/custom-nodes/telegram-ocr/`
- `n8n/custom-nodes/messages-cleanup/`
- `docs/user/run-workflow-in-n8n.md`
- `docs/user/quickstart.md`
- `docs/operator/architecture.md`
- `docs/operator/runbooks.md`
- `tests/integration/test_n8n_custom_node_loading.py`
- tests that directly mention the removed node types

Possible backend cleanup if safe:

- `api/routers/cleanup.py`
- related cleanup router tests

### Detailed Implementation Steps

1. Confirm there are no hidden runtime dependencies on the OCR and cleanup custom node type names beyond docs and tests.
2. Remove `TG Dog OCR` custom node package.
3. Remove `TG Dog Messages Cleanup` custom node package.
4. Update `n8n` custom node loading expectations in integration tests.
5. Rewrite user docs so OCR is shown via built-in `HTTP Request` to `/ocr/messages`.
6. Rewrite user docs so cleanup is shown via built-in transformation nodes, preferably a `Code` node where the logic is too specific for generic field mapping.
7. Review whether `/messages/cleanup` still serves a justified role once the custom node is gone.
8. If `/messages/cleanup` has no remaining product value, remove it and its tests in the same phase.
9. If `/messages/cleanup` still has value as a backend helper for built-in workflows, keep it but stop presenting it as a reason for a custom node.
10. Record the phase decision explicitly so the next phase does not have to guess.
11. Run targeted tests for node loading, docs alignment, OCR router behavior, and any cleanup router behavior still retained.

### Decision Rule For `/messages/cleanup`

This endpoint needs an explicit decision during the phase.

Keep it only if at least one of these is true:

- it remains a useful stable helper endpoint for built-in workflow composition
- it provides reusable formatting logic that would otherwise be copied into docs and examples in an ugly way
- its contract is still aligned with the actual product path

Remove it if all of these are true:

- it is only kept because the removed custom node used it
- the same behavior is easier to express in built-in workflow logic
- keeping it would preserve dead abstractions instead of removing them

Phase 1 implementation note:

- current code inspection shows `/messages/cleanup` is only used by the old cleanup custom node plus its own router test
- unless new evidence appears during implementation, the expected Phase 1 action is to remove `/messages/cleanup`

### Verification

Minimum verification for this phase:

- targeted unit tests for OCR path still pass
- custom-node loading tests no longer expect OCR and cleanup nodes
- user docs no longer instruct people to use the removed nodes
- if cleanup endpoint is removed, its tests are removed or replaced cleanly

Recommended verification:

- run the doc alignment tests
- run the custom-node loading integration test or its updated equivalent
- inspect the `n8n` node type list in a test stack if the integration test already covers it

### Exit Criteria

Phase 1 is complete only when all are true:

- `TG Dog OCR` is gone from runtime, docs, and tests
- `TG Dog Messages Cleanup` is gone from runtime, docs, and tests
- OCR still works through the real API path
- cleanup guidance is replaced with built-in workflow guidance
- there is no ambiguous stale documentation telling users to use the removed nodes

### Stop Condition

Stop immediately after Phase 1 once the exit criteria are met.

Do not start HTML delivery work in the same session.

### Risks

- hidden test coverage may assume these nodes still load in the `n8n` node catalogue
- removing the cleanup endpoint too early may break a path not obvious from docs
- docs may accidentally continue to mention removed nodes in secondary places

## Phase 2: Add Telegram HTML Delivery Support

### Goal

Move Telegram rich-text delivery to `html` and remove MarkdownV2 from the supported delivery contract.

This phase exists because digest replacement should not be finalized while the delivery backend still rejects HTML.

### Why This Is Its Own Phase

This is not a cosmetic tweak. It changes a delivery contract.

Current reality before this phase:

- `POST /post/message` only has a stable plain-text path worth keeping long-term
- legacy MarkdownV2 support existed in parts of the stack and needed removal
- `html` is the intended rich-text target

Desired reality after this phase:

- `html` is an accepted parse mode
- bot-mode delivery supports HTML
- user-mode delivery supports HTML
- MarkdownV2 is no longer part of the delivery contract
- tests reflect this new contract

### Scope

In scope:

- backend parse-mode validation
- bot delivery support for HTML
- Telethon user delivery support for HTML
- tests for router and delivery clients
- docs that describe supported parse modes

Not in scope:

- digest node removal
- OpenCode endpoint redesign
- built-in replacement workflow docs for digest
- HTML-safe chunking logic itself

### Technical Direction

Expected backend changes:

- accept `html` as the only rich-text parse mode
- extend router validation in `api/routers/post_message.py`
- extend bot delivery in `services/shared/telegram/bot_client.py`
- extend Telethon delivery in `services/shared/telegram/client.py`

Important rule:

- do not claim HTML support unless both sender modes have a verified path

If one sender mode cannot support the exact same contract, that must be made explicit in code, tests, and docs.

### Files Likely Touched

- `api/routers/post_message.py`
- `services/shared/telegram/bot_client.py`
- `services/shared/telegram/client.py`
- `api/schemas.py` if parse-mode docs or defaults are clarified there
- `tests/unit/api/test_post_message_router.py`
- `tests/unit/test_telegram_bot_client.py`
- any user or operator docs that describe supported delivery formats

### Detailed Implementation Steps

1. Define the target parse-mode contract for HTML.
2. Add router support so `html` is not rejected as unsupported.
3. Implement bot-mode HTML delivery mapping to Telegram Bot API parse mode.
4. Implement user-mode HTML delivery mapping through Telethon parse mode.
5. Add or update tests for successful HTML delivery in bot mode.
6. Add or update tests for successful HTML delivery in user mode.
7. Update any tests that currently expect `html` to be rejected.
8. Update docs to describe `html` as a supported path and remove MarkdownV2 from the supported contract.

### Verification

Minimum verification:

- unit tests show `html` is accepted by `POST /post/message`
- bot client tests cover HTML parse mode payload generation
- Telethon wrapper tests cover HTML parse mode handling if there is direct unit coverage for this path

Recommended verification:

- targeted manual smoke test against a real Telegram target in a local stack if feasible

### Exit Criteria

Phase 2 is complete only when all are true:

- `html` is a supported parse mode in the backend contract
- both user and bot sender modes have a defined and tested HTML path
- stale tests expecting HTML rejection are updated
- docs no longer describe MarkdownV2 as a supported path

### Stop Condition

Stop after HTML support lands.

Do not start the digest replacement in the same session.

### Risks

- Telegram HTML rules still require careful content shaping; adding parse mode support does not solve chunking safety
- sender-mode differences may force small contract differences that need explicit documentation

## Phase 3: Introduce The Built-In OpenCode Request Flow

### Goal

Introduce the canonical built-in replacement flow for the current digest node's AI step:

- one built-in `HTTP Request` node for prompt assembly plus OpenCode execution
- one built-in `Code` node for Telegram delivery shaping and chunking

This phase is about introducing the replacement path, not removing the old custom digest node yet.

### Why This Must Happen Before Digest Removal

Removing `TG Dog Digest` before a proven replacement exists would create a regression disguised as cleanup.

This phase exists to build the replacement path first, validate it, and only then remove the old node in the next phase.

### Scope

In scope:

- define the API contract for a built-in OpenCode request step
- decide whether to reuse `/digest/messages` temporarily or add a more general endpoint
- define the built-in node recipe for prompt input, system prompt, and content field selection
- implement or refine Telegram HTML-safe shaping logic for built-in `Code`
- document the replacement workflow

Not in scope:

- removing the old digest custom node package
- deleting old digest tests wholesale before replacement coverage exists

### Core Design Requirement

The replacement must feel like one logical AI step in the workflow while still using built-in nodes.

The target user experience should be:

1. one built-in node that calls OpenCode through the API and accepts:
   - source content from an input field or manual text
   - `prompt`
   - `system_prompt`
   - any extra execution options that remain justified
2. one built-in `Code` node that converts AI output into Telegram-ready delivery chunks

This phase should not introduce fake complexity such as splitting prompt creation into a separate mandatory workflow step.

### Open API Contract Decision

This phase must settle one question cleanly:

- keep using `/digest/messages` as the transport contract temporarily
- or introduce a more general endpoint name for OpenCode-backed text processing

Decision rule:

- if the existing endpoint shape can be adapted cleanly without preserving digest-specific naming in user-facing docs, reuse it temporarily
- if the current endpoint semantics are too digest-specific for the new built-in workflow, create a new general endpoint and migrate docs/tests toward it

Do not leave this half-decided.

### Telegram Delivery Shaping Requirement

The built-in `Code` node must produce delivery-safe output for Telegram HTML.

Minimum responsibilities:

- split long text into safe chunks
- avoid splitting in ways that break HTML tags
- preserve obvious block boundaries where practical
- produce a delivery-ready array for downstream send steps

Optional but recommended if still valuable:

- part labels for multi-chunk output
- output metadata such as a normalized parse mode field
- raw AI output preservation for debugging

### Files Likely Touched

Potential backend files:

- `api/routers/digest_llm.py`
- `services/shared/providers/digest.py`
- `api/schemas.py`
- possibly a new router or a renamed generalized route if that is the cleaner contract

Potential docs and tests:

- `docs/user/run-workflow-in-n8n.md`
- `docs/user/quickstart.md`
- digest router tests
- any digest-specific node tests that need replacement-oriented coverage

### Detailed Implementation Steps

1. Define the built-in `HTTP Request` contract for OpenCode-backed text processing.
2. Decide whether to reuse or replace the current digest endpoint name and payload shape.
3. Ensure prompt text is passed in a clean way that still preserves the current worker behavior of sending content via stdin where required.
4. Expose `prompt` and `system_prompt` as first-class request inputs.
5. Define the built-in `Code` node output contract for Telegram delivery shaping.
6. Implement or port the minimum shaping logic needed for HTML-safe chunking.
7. Document the replacement workflow recipe using built-in nodes.
8. Add or update tests that validate the new API contract and the shaping logic.
9. Confirm the replacement path can fully cover the old custom node's real product role before removal begins.

### Verification

Minimum verification:

- API tests cover the new or updated OpenCode text-processing request path
- shaping logic has unit coverage for multi-chunk output
- docs show a complete built-in replacement recipe

Recommended verification:

- manual local workflow smoke test in `n8n` using built-in `HTTP Request` plus built-in `Code`

### Exit Criteria

Phase 3 is complete only when all are true:

- there is a documented and testable built-in replacement flow for `TG Dog Digest`
- that flow uses built-in `HTTP Request` and built-in `Code`
- prompt and system prompt are first-class inputs
- output can be shaped into Telegram-ready HTML-safe chunks
- there is enough confidence to remove the old digest node without leaving users stranded

### Stop Condition

Stop after the replacement path is proven.

Do not remove the old digest custom node in the same session.

### Risks

- endpoint naming may remain misleading if left half-modernized
- HTML-safe chunking can become deceptively complex if done carelessly
- replacing the node before the built-in recipe is clearly documented would create avoidable confusion

## Phase 4: Remove `TG Dog Digest` And Finish The Cleanup

### Goal

Remove the digest custom node and finish all remaining cleanup related to this milestone.

By the time this phase starts, the replacement path must already exist and be documented.

### Scope

In scope:

- remove `TG Dog Digest` custom node package
- remove digest custom-node loading expectations from tests
- replace remaining docs that still mention the old digest node
- remove stale digest-node-specific tests that only validate the old wrapper behavior
- clean up backend naming or compatibility paths if they are no longer justified

Not in scope:

- starting a new milestone for bridge-node removal
- redesigning OCR or Telegram runtime architecture

### Cleanup Principle

This phase should remove obsolete structure, not just hide it.

That means:

- delete stale docs instead of letting them rot
- delete stale tests that only describe dead node behavior
- remove dead references from architecture docs and runbooks
- keep only compatibility code that has a real current consumer

### Files Likely Touched

- `n8n/custom-nodes/telegram-digest/`
- `tests/unit/test_telegram_digest_node.py`
- `tests/integration/test_n8n_custom_node_loading.py`
- `docs/user/run-workflow-in-n8n.md`
- `docs/user/quickstart.md`
- `docs/operator/architecture.md`
- `docs/operator/runbooks.md`
- any other references surfaced by grep during the phase

Potential backend cleanup:

- old digest endpoint names, request schemas, or response shapes that only exist for the removed node

### Detailed Implementation Steps

1. Remove the digest custom node package.
2. Remove digest node references from node loading tests.
3. Replace remaining user docs with the built-in workflow recipe from Phase 3.
4. Remove or rewrite digest-node-specific unit tests.
5. Review backend route and schema names for stale digest-only semantics.
6. Remove dead compatibility code only if the built-in replacement no longer depends on it.
7. Run final targeted tests for docs, node loading, delivery shaping, and the AI request path.

### Verification

Minimum verification:

- no runtime docs instruct users to use `TG Dog Digest`
- no test suite expects the digest custom node to load
- built-in replacement path remains documented and tested

Recommended verification:

- run a final integration pass covering the updated custom-node loading expectations
- run a manual end-to-end workflow smoke test if feasible

### Exit Criteria

Phase 4 is complete only when all are true:

- `TG Dog Digest` is gone from runtime, docs, and tests
- replacement built-in workflow docs are the canonical path
- stale digest-specific abstractions no longer define the project story

### Stop Condition

This is the final stop point for the milestone.

After this phase, the milestone can be reviewed and closed.

### Risks

- stale references in docs and tests are easy to miss because the digest node is mentioned in many places
- removing old backend naming too aggressively could break the newly documented built-in flow if it still depends on that contract

## Cross-Phase Guardrails

These rules apply in every phase.

### Guardrail 1: Preserve real integrations

Never replace a real runtime path with a fake or placeholder one just to reduce custom code.

### Guardrail 2: Smallest viable correct change

Within a phase, prefer the smallest correct change that fully completes the phase.

### Guardrail 3: Docs and tests move with runtime

If a phase changes runtime truth, update docs and tests in that same phase.

### Guardrail 4: No stealth architecture migrations

Do not smuggle major runtime moves into a cleanup phase. Examples of forbidden stealth moves in this milestone:

- moving OpenCode into `n8n`
- moving OCR into `n8n`
- changing Telegram auth storage strategy

### Guardrail 5: Stop after each phase

Do not keep going just because there is still energy left in the session.

The entire point of this plan is to keep context bounded and avoid tangled multi-phase edits.

## Suggested Verification Commands By Phase

These are suggestions, not a mandatory exact list. Each phase can narrow or expand them depending on what actually changed.

Phase 1 candidates:

- `docker compose run --rm api pytest tests/unit/api/test_ocr_router.py`
- `docker compose run --rm api pytest tests/integration/test_n8n_custom_node_loading.py`
- `docker compose run --rm api pytest tests/integration/test_n8n_docs_alignment.py`

Phase 2 candidates:

- `docker compose run --rm api pytest tests/unit/api/test_post_message_router.py`
- `docker compose run --rm api pytest tests/unit/test_telegram_bot_client.py`

Phase 3 candidates:

- targeted API tests for the OpenCode request route
- targeted unit tests for shaping and chunking logic

Phase 4 candidates:

- `docker compose run --rm api pytest tests/integration/test_n8n_custom_node_loading.py`
- `docker compose run --rm api pytest tests/integration/test_n8n_docs_alignment.py`
- any updated digest replacement tests introduced in Phase 3

## Open Questions To Revisit Only If Needed

These are not blockers right now, but they may need explicit answers during implementation.

- Should `/messages/cleanup` survive as a helper endpoint after the node is gone, or should the cleanup responsibility move fully into built-in workflow logic?
- Should `/digest/messages` be retained as a compatibility route while the built-in replacement is introduced, or should a more general endpoint replace it?
- How much output metadata beyond `delivery_chunks` is still justified once the built-in shaping step becomes canonical?

## Completion Definition For The Entire Milestone

This milestone is complete only when all are true:

- `TG Dog OCR` is removed
- `TG Dog Messages Cleanup` is removed
- `TG Dog Digest` is removed
- Telegram HTML delivery is supported in the backend
- the built-in `HTTP Request` plus `Code` recipe is the documented AI workflow path
- docs describe the surviving custom nodes as intentional bridge nodes, not historical leftovers
- tests reflect the new runtime truth

## Future Follow-Up After This Milestone

After this milestone is done, a separate review can assess the remaining custom nodes:

- `TG Dog Source Selector`
- `TG Dog Message Reader`
- `TG Dog Post Message`

That follow-up should ask a harder question:

"Are these still justified bridge nodes, or can any of them be reduced further without damaging the real Telegram product path?"

That is a different milestone and should not be mixed into this one by accident.
