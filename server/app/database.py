from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from dotenv import load_dotenv

load_dotenv()

import os

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set."
    )

engine = create_engine(
    DATABASE_URL,
    echo=False,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()