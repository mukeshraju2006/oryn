"""Regression tests for workspace and snapshot lifecycle operations."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-123456")

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from server.app.database import Base
from server.app.models.snapshot import Snapshot
from server.app.models.user import User
from server.app.models.workspace import Workspace
from server.app.routes.snapshots import delete_snapshot
from server.app.routes.workspaces import rename_workspace, delete_workspace


@pytest.fixture
def db_and_user():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(email="owner@example.test", password_hash="unused")
    stranger = User(email="stranger@example.test", password_hash="unused")
    db.add_all([user, stranger])
    db.commit()
    db.refresh(user)
    db.refresh(stranger)
    workspace = Workspace(user_id=user.id, name="Original")
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    yield db, user, stranger, workspace
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_rename_workspace_trims_name_and_rejects_empty(db_and_user):
    db, user, _, workspace = db_and_user
    result = rename_workspace(workspace.id, {"name": "  Renamed  "}, db, user)
    assert result["name"] == "Renamed"
    with pytest.raises(HTTPException) as error:
        rename_workspace(workspace.id, {"name": "  "}, db, user)
    assert error.value.status_code == 422


def test_workspace_rename_and_delete_are_owner_scoped(db_and_user):
    db, user, stranger, workspace = db_and_user
    with pytest.raises(HTTPException) as error:
        rename_workspace(workspace.id, {"name": "Stolen"}, db, stranger)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        delete_workspace(workspace.id, db, stranger)
    assert error.value.status_code == 404


def test_deleting_workspace_removes_its_snapshots(db_and_user):
    db, user, _, workspace = db_and_user
    db.add(Snapshot(workspace_id=workspace.id, version=1, data={"application": "vscode"}))
    db.commit()
    result = delete_workspace(workspace.id, db, user)
    assert result["deleted"] is True
    assert db.scalar(select(Workspace).where(Workspace.id == workspace.id)) is None
    assert db.scalars(select(Snapshot).where(Snapshot.workspace_id == workspace.id)).all() == []


def test_delete_snapshot_is_scoped_to_workspace_and_owner(db_and_user):
    db, user, stranger, workspace = db_and_user
    snapshot = Snapshot(workspace_id=workspace.id, version=1, data={"application": "vscode"})
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    with pytest.raises(HTTPException) as error:
        delete_snapshot(workspace.id, snapshot.id, db, stranger)
    assert error.value.status_code == 404
    result = delete_snapshot(workspace.id, snapshot.id, db, user)
    assert result == {"deleted": True, "snapshot_id": snapshot.id}
    assert db.get(Snapshot, snapshot.id) is None
