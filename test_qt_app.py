"""Headless smoke tests for the modern Qt desktop UI."""
import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton
from urllib.error import HTTPError

from gui.qt_app import AuthView, DashboardView, error_message


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_auth_view_toggles_registration_fields(qt_app):
    view = AuthView()
    assert view.confirm_password.isHidden()
    view.toggle_mode()
    assert not view.confirm_password.isHidden()
    assert view.submit_button.text().startswith("Create account")
    view.toggle_mode()
    assert view.confirm_password.isHidden()
    view.close()


def test_auth_form_requires_credentials(qt_app):
    view = AuthView()
    view.submit()
    assert view.message.text() == "Enter your email and password."
    view.close()


def test_http_error_shows_safe_api_detail():
    error = HTTPError(
        "https://example.invalid/auth/login",
        401,
        "Unauthorized",
        {},
        io.BytesIO(b'{"detail":"Invalid email or password"}'),
    )
    assert error_message(error) == "API error 401: Invalid email or password"



def test_dashboard_snapshot_rows_have_restore_details_and_delete(qt_app, monkeypatch):
    monkeypatch.setattr(DashboardView, "load_workspaces", lambda self: None)

    class DummyClient:
        base_url = "https://example.invalid"

    view = DashboardView(DummyClient())
    view.workspace_id = 17
    view.snapshots = [{
        "id": 101,
        "snapshot_number": 1,
        "application": "vscode",
        "created_at": "2026-10-25T12:00:00",
        "version": 5,
        "file_count": 3,
        "project_path": "/tmp/demo",
    }]
    view._render_snapshots()

    assert view.snapshot_table.columnCount() == 7
    assert view.snapshot_table.rowCount() == 1
    actions = view.snapshot_table.cellWidget(0, 6)
    assert actions is not None
    assert {button.text() for button in actions.findChildren(QPushButton)} >= {
        "Restore", "Details", "Delete"
    }
    assert view.snapshot_table.item(0, 0).data(Qt.UserRole) == 101
    view.close()


def test_url_error_includes_readable_reason():
    from urllib.error import URLError

    assert "Temporary failure" in error_message(URLError("Temporary failure"))
