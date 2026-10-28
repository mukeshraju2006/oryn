"""Regression tests for verified chunked snapshot uploads."""
import base64
import hashlib
import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-123456")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from server.app.database import Base
from server.app.models.snapshot import Snapshot
from server.app.models.snapshot_upload import SnapshotUploadChunk
from server.app.models.user import User
from server.app.models.workspace import Workspace
from server.app.routes.snapshot_uploads import (\n    CHUNK_BYTES,
    begin_snapshot_upload,
    finalize_snapshot_upload,
    put_snapshot_chunk,
    snapshot_download_manifest,
    snapshot_download_chunk,
)


@pytest.fixture
def db_and_user():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(email="chunk-owner@example.test", password_hash="unused")
    db.add(user)
    db.commit()
    db.refresh(user)
    workspace = Workspace(user_id=user.id, name="Chunk test")
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    yield db, user, workspace
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def make_payload():
    payload = {
        "version": 5,
        "application": "vscode",
        "workspace": {"path": "/tmp/project"},
        "files": [],
        "browser_urls": [],
        "project": {
            "root": ".",
            "directories": [],
            "files": [{"path": "hello.txt", "data": "aGVsbG8=", "size": 5, "encoding": "base64"}],
        },
    }
    canonical = json.dumps(
        payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    payload["_integrity"] = {
        "algorithm": "sha256",
        "digest": hashlib.sha256(canonical).hexdigest(),
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def test_chunked_upload_verifies_full_payload_and_finalize_is_idempotent(db_and_user):
    db, user, workspace = db_and_user
    raw = make_payload()
    upload = begin_snapshot_upload(
        workspace.id,
        {
            "total_bytes": len(raw),
            "chunk_count": 1,
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        db,
        user,
    )
    chunk = raw
    put_snapshot_chunk(
        workspace.id,
        upload["upload_id"],
        0,
        {
            "sha256": hashlib.sha256(chunk).hexdigest(),
            "data": base64.b64encode(chunk).decode("ascii"),
        },
        db,
        user,
    )

    first = finalize_snapshot_upload(workspace.id, upload["upload_id"], db, user)
    second = finalize_snapshot_upload(workspace.id, upload["upload_id"], db, user)

    assert first["verified"] is True
    assert first["uploaded_bytes"] == len(raw)
    assert second["id"] == first["id"]
    assert second["already_finalized"] is True
    saved = db.get(Snapshot, first["id"])
    assert saved.data["project"]["files"][0]["path"] == "hello.txt"
    assert db.scalars(select(SnapshotUploadChunk)).all() == []


def test_incomplete_upload_cannot_create_a_snapshot(db_and_user):
    db, user, workspace = db_and_user
    raw = make_payload()
    upload = begin_snapshot_upload(
        workspace.id,
        {
            "total_bytes": len(raw),
            "chunk_count": 1,
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        db,
        user,
    )
    with pytest.raises(HTTPException) as error:
        finalize_snapshot_upload(workspace.id, upload["upload_id"], db, user)
    assert error.value.status_code == 409
    assert db.scalars(select(Snapshot)).all() == []


def test_large_snapshot_download_manifest_and_chunks_are_checksummed(db_and_user):
    db, user, workspace = db_and_user
    payload = {
        "version": 5,
        "application": "vscode",
        "workspace": {"path": "/tmp/project"},
        "files": [],
        "browser_urls": [],
        "project": {
            "root": ".",
            "directories": [],
            "files": [{
                "path": "large.bin",
                "data": "z" * (600_000),
                "size": 600_000,
                "encoding": "base64",
            }],
        },
    }
    snapshot = Snapshot(workspace_id=workspace.id, version=5, data=payload)
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    manifest = snapshot_download_manifest(workspace.id, snapshot.id, db, user)
    assert manifest["total_bytes"] > manifest["chunk_bytes"]
    assert manifest["chunk_count"] == 2

    parts = []
    for index in range(manifest["chunk_count"]):
        part = snapshot_download_chunk(workspace.id, snapshot.id, index, db, user)
        chunk = base64.b64decode(part["data"], validate=True)
        assert hashlib.sha256(chunk).hexdigest() == part["sha256"]
        parts.append(chunk)
    restored = b"".join(parts)
    assert hashlib.sha256(restored).hexdigest() == manifest["sha256"]
    assert json.loads(restored.decode("utf-8"))["project"]["files"][0]["path"] == "large.bin"


def test_snapshot_download_is_scoped_to_workspace_owner(db_and_user):
    db, user, workspace = db_and_user
    stranger = User(email="chunk-stranger@example.test", password_hash="unused")
    db.add(stranger)
    db.commit()
    db.refresh(stranger)
    snapshot = Snapshot(workspace_id=workspace.id, version=1, data={"version": 1})
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    with pytest.raises(HTTPException) as error:
        snapshot_download_manifest(workspace.id, snapshot.id, db, stranger)
    assert error.value.status_code == 404
