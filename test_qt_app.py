"""Headless smoke tests for the modern Qt desktop UI."""
import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from urllib.error import HTTPError

from gui.qt_app import AuthView, error_message


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
