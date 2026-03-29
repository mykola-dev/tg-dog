import json

from services.shared.cli import build_error_envelope, build_success_envelope


def test_build_success_envelope_has_required_fields() -> None:
    envelope = build_success_envelope(
        node_name="fetch",
        run_id="run-123",
        payload_inline={"items": 1},
        warnings=["w1"],
        metrics={"duration_ms": 10},
    )

    encoded = json.dumps(envelope.model_dump(mode="json"))
    parsed = json.loads(encoded)

    assert parsed["contract_version"] == "v1"
    assert parsed["node_name"] == "fetch"
    assert parsed["run_id"] == "run-123"
    assert parsed["status"] == "ok"
    assert parsed["payload_inline"] == {"items": 1}
    assert parsed["warnings"] == ["w1"]
    assert parsed["metrics"] == {"duration_ms": 10}
    assert parsed["error"] is None


def test_build_error_envelope_sets_error_payload() -> None:
    envelope = build_error_envelope(
        node_name="fetch",
        run_id="run-123",
        code="E_FETCH",
        message="failed",
        retryable=True,
        user_action_required=False,
        details={"hint": "retry"},
        recommended_action="Retry later",
    )

    dumped = envelope.model_dump(mode="json")
    assert dumped["status"] == "error"
    assert dumped["error"]["code"] == "E_FETCH"
    assert dumped["error"]["retryable"] is True
    assert dumped["error"]["recommended_action"] == "Retry later"
