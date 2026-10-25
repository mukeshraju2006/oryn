"""Request validation regression tests for authentication."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-123456")

import pytest
from pydantic import ValidationError

from server.app.routes.auth import Credentials, RegistrationCredentials


def test_registration_normalizes_email():
    payload = RegistrationCredentials(email="  User@Example.COM ", password="long-enough")
    assert payload.email == "user@example.com"


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("not-an-email", "long-enough"),
        ("user@example.com", "short"),
        ("", "long-enough"),
    ],
)
def test_registration_rejects_invalid_credentials(email, password):
    with pytest.raises(ValidationError):
        RegistrationCredentials(email=email, password=password)


def test_login_rejects_missing_password():
    with pytest.raises(ValidationError):
        Credentials.model_validate({"email": "user@example.com"})


def test_login_email_is_normalized():
    payload = Credentials(email="User@Example.com", password="x")
    assert payload.email == "user@example.com"
