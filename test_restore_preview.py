"""Regression test for metadata-first restore preview."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from gui.qt_app import DashboardView


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_restore_starts_with_local_manifest_comparison(qt_app, monkeypatch):
    """The first restore request fetches a lightweight manifest, not the full payload."""
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

    assert captured["activity"] == "Comparing local workspace with cloud snapshot…"
    assert captured["kwargs"] == {}
    # The callback is deferred; previewing metadata does not call get_snapshot.
    assert callable(captured["function"])
    view.close()
