from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_repo_does_not_ship_repo_managed_n8n_workflows() -> None:
    workflow_dir = ROOT / "n8n" / "workflows"
    assert workflow_dir.exists()
    assert sorted(path.name for path in workflow_dir.glob("*.json")) == []
