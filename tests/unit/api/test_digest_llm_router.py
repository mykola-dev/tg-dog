from unittest.mock import patch


def test_digest_llm_router_returns_digest(stateless_api_client):
    with patch("api.routers.digest_llm.run_digest_command") as mock_runner:
        mock_runner.return_value.success = True
        mock_runner.return_value.output_text = "# Digest\n\n- Item with [link](https://example.com)"
        mock_runner.return_value.provider_id = "opencode_cli"
        mock_runner.return_value.details = {"ok": True}

        resp = stateless_api_client.post(
            "/digest/messages",
            json={
                "formatted_text": "## Example\n\nHello",
                "command_template": 'opencode run -m opencode/minimax-m2.5-free "{prompt}"',
                "system_prompt": "Create digest",
                "output_format": "markdown_v2",
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["parse_mode"] == "markdown_v2"
    assert payload["delivery_chunks"]
    assert payload["digest_text"] == "*Digest*\n\n\\- Item with [link](https://example.com)"
    assert payload["provider_id"] == "opencode_cli"


def test_digest_llm_router_returns_503_on_provider_failure(stateless_api_client):
    with patch("api.routers.digest_llm.run_digest_command") as mock_runner:
        mock_runner.return_value.success = False
        mock_runner.return_value.output_text = None
        mock_runner.return_value.provider_id = "opencode_cli"
        mock_runner.return_value.details = {"error": "failed"}

        resp = stateless_api_client.post(
            "/digest/messages",
            json={
                "formatted_text": "## Example\n\nHello",
                "command_template": 'opencode run -m opencode/minimax-m2.5-free "{prompt}"',
                "system_prompt": "Create digest",
                "output_format": "markdown_v2",
            },
        )

    assert resp.status_code == 503
    assert resp.json()["provider_id"] == "opencode_cli"


def test_digest_llm_router_normalizes_legacy_markdown_alias(stateless_api_client):
    with patch("api.routers.digest_llm.run_digest_command") as mock_runner:
        mock_runner.return_value.success = True
        mock_runner.return_value.output_text = "- Item"
        mock_runner.return_value.provider_id = "opencode_cli"
        mock_runner.return_value.details = {"ok": True}

        resp = stateless_api_client.post(
            "/digest/messages",
            json={
                "formatted_text": "## Example\n\nHello",
                "command_template": 'opencode run -m opencode/minimax-m2.5-free "{prompt}"',
                "system_prompt": "Create digest",
                "output_format": "markdown",
            },
        )

    assert resp.status_code == 400
    assert resp.json()["code"] == "DIGEST_OUTPUT_FORMAT_UNSUPPORTED"
