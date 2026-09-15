from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt


# CHANGED: Authentication configuration
SECRET_KEY = "oryn-development-secret-change-this"
ALGORITHM = "HS256"


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

    return {
        "id": user.id,
        "email": user.email,
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

    # CHANGED: Create JWT containing the user ID
    token = jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return {
        "access_token": token,
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
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        user_id = payload.get("sub")

        if not user_id:
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