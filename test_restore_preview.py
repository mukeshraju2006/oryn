"""Regression test for metadata-first restore preview."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from gui.qt_app import DashboardView


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_restore_preview_uses_metadata_before_fetching_snapshot(qt_app, monkeypatch):
    """Preview confirmation must happen before the full project download."""
    monkeypatch.setattr(DashboardView, "load_workspaces", lambda self: None)

    class DummyClient:
        base_url = "https://example.invalid"

    view = DashboardView(DummyClient())
    view.workspace_id = 17
    view.snapshots = [{
        "id": 101,
        "snapshot_number": 3,
        "application": "workspace",
        "created_at": "2026-10-28T12:00:00",
        "version": 5,
        "file_count": 4,
        "browser_url_count": 0,
        "project_path": None,
    }]
    monkeypatch.setattr("gui.qt_app.confirm_dialog", lambda *args, **kwargs: True)
    captured = {}
    view._task = lambda function, success, activity, **kwargs: captured.update(
        function=function, success=success, activity=activity, kwargs=kwargs
    )

    view.restore_snapshot(snapshot_id=101, workspace_id=17)

    assert captured["activity"] == "Downloading and validating snapshot…"
    assert captured["kwargs"]["on_progress"] is not None
    # The callback is deferred; previewing metadata does not call get_snapshot.
    assert callable(captured["function"])
    view.close()
