"""Headless smoke tests for the modern Qt desktop UI."""
import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton
from urllib.error import HTTPError

from gui.qt_app import AuthView, DashboardView, Task, TaskCancelled, confirm_dialog, error_message, show_message_dialog


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
    view._filter_snapshots("/tmp/demo")
    assert not view.snapshot_table.isRowHidden(0)
    view._filter_snapshots("does-not-exist")
    assert view.snapshot_table.isRowHidden(0)
    assert not view.snapshot_empty_label.isHidden()
    view.close()


def test_url_error_includes_readable_reason():
    from urllib.error import URLError

    assert "Temporary failure" in error_message(URLError("Temporary failure"))



def test_long_task_cancellation_is_checked_at_safe_progress_points():
    task = Task(lambda progress: progress("checkpoint"), report_progress=True)
    task.request_cancel()
    with pytest.raises(TaskCancelled, match="cancelled"):
        task.report_progress("checkpoint")



def test_confirmation_dialog_has_explicit_action_labels(qt_app):
    from gui.qt_app import confirm_dialog
    from PySide6.QtCore import QTimer

    from gui.qt_app import QDialog, QPushButton

    def inspect_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        labels = {button.text() for button in dialog.findChildren(QPushButton)}
        assert "Cancel" in labels
        assert "Delete snapshot" in labels
        dialog.reject()

    QTimer.singleShot(0, inspect_dialog)
    assert confirm_dialog(
        None, "Delete snapshot",
        "Permanently delete Snapshot 4?",
        confirm_label="Delete snapshot", destructive=True,
    ) is False


def test_message_dialog_shows_body_and_close_action(qt_app):
    from PySide6.QtCore import QTimer
    from gui.qt_app import QDialog, QLabel

    def inspect_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        assert any(label.text() == "A readable message" for label in dialog.findChildren(QLabel))
        assert any(button.text() == "Close" for button in dialog.findChildren(QPushButton))
        dialog.accept()

    QTimer.singleShot(0, inspect_dialog)
    show_message_dialog(None, "Test dialog", "A readable message")
