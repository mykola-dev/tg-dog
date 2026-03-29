from pathlib import Path


def test_node_toggle_settings_persist_across_loads(tmp_path: Path) -> None:
    from services.shared.runtime.node_toggles import load_node_toggles, save_node_toggles

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    save_node_toggles(workspace, {"ocr": True, "classification": False})
    loaded = load_node_toggles(workspace)

    assert loaded["ocr"] is True
    assert loaded["classification"] is False


def test_node_toggle_defaults_when_file_missing(tmp_path: Path) -> None:
    from services.shared.runtime.node_toggles import load_node_toggles

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    loaded = load_node_toggles(workspace)
    assert loaded == {"ocr": False, "classification": False}
