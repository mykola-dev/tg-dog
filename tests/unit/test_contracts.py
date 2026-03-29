from datetime import datetime

import pytest
from pydantic import ValidationError

from services.shared.contracts.common import AdapterEnvelope, StructuredError
from services.shared.contracts.message import CanonicalMessage
from services.shared.contracts.run import RunManifest


def test_run_manifest_requires_trigger_type() -> None:
    with pytest.raises(ValidationError):
        RunManifest.model_validate({"run_id": "123"})


def test_message_rejects_unknown_source_kind() -> None:
    with pytest.raises(ValidationError):
        CanonicalMessage.model_validate(
            {
                "schema_version": "v1",
                "source_kind": "unknown",
                "source_id": "1",
                "source_title": "Example",
                "message_id": "2",
                "message_timestamp": "2026-03-21T10:00:00Z",
                "is_outbound": False,
                "is_from_self": False,
                "is_service_message": False,
                "media_items": [],
                "ingestion_meta": {},
            }
        )


def test_adapter_error_envelope_requires_status_and_error_fields() -> None:
    with pytest.raises(ValidationError):
        AdapterEnvelope.model_validate(
            {
                "contract_version": "v1",
                "node_name": "fetch",
                "run_id": "run-1",
                "status": "error",
                "payload_inline": None,
                "payload_ref": None,
                "warnings": [],
                "metrics": {},
            }
        )

    envelope = AdapterEnvelope.model_validate(
        {
            "contract_version": "v1",
            "node_name": "fetch",
            "run_id": "run-1",
            "status": "error",
            "payload_inline": None,
            "payload_ref": None,
            "warnings": [],
            "metrics": {},
            "error": StructuredError(
                code="E_TEST",
                message="test",
                retryable=False,
                user_action_required=False,
                details={"when": datetime.now().isoformat()},
            ).model_dump(),
        }
    )
    assert envelope.status == "error"
    assert envelope.error is not None
