"""Cross-platform regression tests for explicit workspace capture exclusions."""
from pathlib import Path

import pytest

from oryn.applications.vscode.adapter import VSCodeAdapter


def test_project_capture_reports_policy_exclusions(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    dependency = root / "node_modules"
    dependency.mkdir()
    (dependency / "package.js").write_text("generated", encoding="utf-8")

    adapter = VSCodeAdapter.__new__(VSCodeAdapter)
    result = adapter.capture_project(root, files=[])

    captured_paths = {item["path"] for item in result["files"]}
    assert "main.py" in captured_paths
    assert ".env" not in captured_paths
    assert not any(path.startswith("node_modules/") for path in captured_paths)
    assert ".env" in result["omitted_files"]
    assert "node_modules/" in result["omitted_files"]
    assert "credential/private-key" in result["exclusion_reasons"][".env"]
    assert "dependency/cache/build" in result["exclusion_reasons"]["node_modules/"]


def test_project_capture_fails_for_missing_workspace(tmp_path):
    adapter = VSCodeAdapter.__new__(VSCodeAdapter)
    with pytest.raises(FileNotFoundError, match="Workspace directory"):
        adapter.capture_project(tmp_path / "does-not-exist", files=[])
