"""Authentication endpoints with explicit request validation."""
import os
import re
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.app.database import get_db
from server.app.models.user import User

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(hours=12)
INSECURE_SECRET_VALUES = {
    "",
    "change-this-to-a-secure-random-secret",
    "oryn-development-secret-change-this",
    "replace-with-a-random-secret-at-least-32-characters",
}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid email address.")
        return value


class RegistrationCredentials(Credentials):
    password: str = Field(min_length=8, max_length=128)


def _get_secret_key() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if (
        len(secret) < 32
        or secret in INSECURE_SECRET_VALUES
        or secret.lower().startswith(
            ("change-this", "replace-with", "oryn-development")
        )
    ):
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured. Set JWT_SECRET to a random secret of at least 32 characters.",
        )
    return secret


def _create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + ACCESS_TOKEN_TTL,
        },
        _get_secret_key(),
        algorithm=ALGORITHM,
    )


router = APIRouter(prefix="/auth", tags=["auth"])
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@router.post("/register")
def register(data: RegistrationCredentials, db: Session = Depends(get_db)):
    # Check configuration before writing a user row.
    _get_secret_key()

    existing_user = db.scalar(select(User).where(User.email == data.email))
    if existing_user:
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(
        email=data.email,
        password_hash=password_hash.hash(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Concurrent registrations can race on the unique email constraint.
        existing_user = db.scalar(select(User).where(User.email == data.email))
        if existing_user:
            raise HTTPException(status_code=409, detail="User already exists")
        raise
    db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "access_token": _create_access_token(user),
        "token_type": "bearer",
    }


@router.post("/login")
def login(data: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email))
    if user is None or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "access_token": _create_access_token(user),
        "token_type": "bearer",
    }


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            token,
            _get_secret_key(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
        user_id = payload.get("sub")
        if not isinstance(user_id, str) or not user_id.isdigit():
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get(User, int(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
