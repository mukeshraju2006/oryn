"""Database engine configuration for local and serverless deployments."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()


def normalize_database_url(value: str) -> str:
    """Use psycopg v3 explicitly; Neon commonly supplies generic postgres URLs."""
    value = value.strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


_raw_database_url = os.getenv("DATABASE_URL", "").strip()
if not _raw_database_url:
    raise RuntimeError("DATABASE_URL environment variable is not set.")

DATABASE_URL = normalize_database_url(_raw_database_url)
_is_postgres = DATABASE_URL.startswith("postgresql+psycopg://")

engine_options = {
    "echo": False,
    "pool_pre_ping": True,
}
if _is_postgres:
    # Short-lived serverless instances should not hold stale connections.
    engine_options.update(
        pool_recycle=300,
        connect_args={"connect_timeout": 10},
    )

engine = create_engine(DATABASE_URL, **engine_options)

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
