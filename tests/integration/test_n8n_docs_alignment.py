from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_quickstart_points_to_current_n8n_url_and_empty_workspace_start() -> None:
    text = _text("docs/user/quickstart.md")
    assert "http://localhost:50000" in text
    assert "New Workflow" in text
    assert "starter-workflow" not in text


def test_quickstart_points_to_current_workflow_guide() -> None:
    text = _text("docs/user/quickstart.md")
    assert "docs/user/run-workflow-in-n8n.md" in text


def test_historical_superpowers_docs_are_removed() -> None:
    assert not (ROOT / "docs/superpowers").exists()
