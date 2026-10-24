import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt


ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(hours=12)
INSECURE_SECRET_VALUES = {
    "",
    "change-this-to-a-secure-random-secret",
    "oryn-development-secret-change-this",
    "replace-with-a-random-secret-at-least-32-characters",
}


def _get_secret_key():
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


def _create_access_token(user):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "iat": now,
            "exp": now + ACCESS_TOKEN_TTL,
        },
        _get_secret_key(),
        algorithm=ALGORITHM,
    )


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


# CHANGED: Password hashing
password_hash = PasswordHash.recommended()


# CHANGED: Reads Bearer token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)


@router.post("/register")
def register(
    data: dict,
    db: Session = Depends(
        __import__(
            "server.app.database",
            fromlist=["get_db"],
        ).get_db
    ),
):

    from server.app.models.user import User

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        raise HTTPException(
            status_code=400,
            detail="email and password are required",
        )

    existing_user = db.scalar(
        select(User).where(
            User.email == email
        )
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="User already exists",
        )

    user = User(
        email=email,
        password_hash=password_hash.hash(
            password
        ),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Return the same authentication contract as login. The desktop
    # client immediately persists access_token after registration.
    return {
        "id": user.id,
        "email": user.email,
        "access_token": _create_access_token(user),
        "token_type": "bearer",
    }


@router.post("/login")
def login(
    data: dict,
    db: Session = Depends(
        __import__(
            "server.app.database",
            fromlist=["get_db"],
        ).get_db
    ),
):

    from server.app.models.user import User

    email = data.get("email")
    password = data.get("password")

    user = db.scalar(
        select(User).where(
            User.email == email
        )
    )

    if (
        user is None
        or not password_hash.verify(
            password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    return {
        "access_token": _create_access_token(user),
        "token_type": "bearer",
    }


# CHANGED: Get authenticated user
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(
        __import__(
            "server.app.database",
            fromlist=["get_db"],
        ).get_db
    ),
):

    from server.app.models.user import User

    try:

        payload = jwt.decode(
            token,
            _get_secret_key(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )

        user_id = payload.get("sub")
        if not isinstance(user_id, str) or not user_id.isdigit():
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
            )

    except jwt.InvalidTokenError:

        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    user = db.get(
        User,
        int(user_id),
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    return user