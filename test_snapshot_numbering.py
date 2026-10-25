"""Regression tests for workspace-scoped snapshot numbering."""

import os

import pytest
from fastapi import HTTPException

# The route imports the database module at import time. Use a harmless local
# SQLite URL for these tests; no external database is contacted.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-123456")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from server.app.database import Base
from server.app.models.snapshot import Snapshot
from server.app.models.user import User
from server.app.models.workspace import Workspace
from server.app.routes.snapshots import create_snapshot, list_snapshots


def test_snapshot_numbers_reset_for_each_workspace_and_user():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        user_one = User(email="one@example.test", password_hash="unused")
        user_two = User(email="two@example.test", password_hash="unused")
        db.add_all([user_one, user_two])
        db.commit()
        db.refresh(user_one)
        db.refresh(user_two)

        one_workspace_a = Workspace(user_id=user_one.id, name="A")
        one_workspace_b = Workspace(user_id=user_one.id, name="B")
        two_workspace_a = Workspace(user_id=user_two.id, name="A")
        db.add_all([one_workspace_a, one_workspace_b, two_workspace_a])
        db.commit()
        db.refresh(one_workspace_a)
        db.refresh(one_workspace_b)
        db.refresh(two_workspace_a)

        first = create_snapshot(
            one_workspace_a.id, {"version": 5}, db, user_one
        )
        other_users_first = create_snapshot(
            two_workspace_a.id, {"version": 5}, db, user_two
        )
        other_workspace_first = create_snapshot(
            one_workspace_b.id, {"version": 5}, db, user_one
        )
        second = create_snapshot(
            one_workspace_a.id, {"version": 5}, db, user_one
        )

        assert first["snapshot_number"] == 1
        assert other_users_first["snapshot_number"] == 1
        assert other_workspace_first["snapshot_number"] == 1
        assert second["snapshot_number"] == 2

        user_one_a = list_snapshots(one_workspace_a.id, db, user_one)
        user_one_b = list_snapshots(one_workspace_b.id, db, user_one)
        user_two_a = list_snapshots(two_workspace_a.id, db, user_two)

        assert [item["snapshot_number"] for item in user_one_a] == [2, 1]
        assert [item["snapshot_number"] for item in user_one_b] == [1]
        assert [item["snapshot_number"] for item in user_two_a] == [1]

        # The internal database ID remains unique even when display numbers match.
        assert first["id"] != other_users_first["id"]
        assert first["snapshot_number"] == other_users_first["snapshot_number"]

    Base.metadata.drop_all(engine)
    engine.dispose()



def test_future_snapshot_format_is_rejected():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="future@example.test", password_hash="unused")
        db.add(user)
        db.commit()
        db.refresh(user)
        workspace = Workspace(user_id=user.id, name="Future")
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        with pytest.raises(HTTPException) as error:
            create_snapshot(workspace.id, {"version": 6}, db, user)
        assert error.value.status_code == 422
    Base.metadata.drop_all(engine)
    engine.dispose()



def test_invalid_snapshot_structure_is_rejected():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="shape@example.test", password_hash="unused")
        db.add(user)
        db.commit()
        db.refresh(user)
        workspace = Workspace(user_id=user.id, name="Shape")
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        with pytest.raises(HTTPException) as error:
            create_snapshot(workspace.id, {"version": 5, "workspace": []}, db, user)
        assert error.value.status_code == 422
    Base.metadata.drop_all(engine)
    engine.dispose()
