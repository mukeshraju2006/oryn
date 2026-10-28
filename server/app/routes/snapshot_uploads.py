"""Resumable snapshot uploads for payloads larger than the gateway limit."""
import base64
import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from server.app.database import get_db
from server.app.models.snapshot import Snapshot
from server.app.models.snapshot_upload import SnapshotUpload, SnapshotUploadChunk
from server.app.models.user import User
from server.app.models.workspace import Workspace
from server.app.routes.auth import get_current_user

router = APIRouter(prefix="/workspaces", tags=["snapshot uploads"])

# CHANGED: Keep each HTTP request small; the full payload can be much larger.
CHUNK_BYTES = 512 * 1024
MAX_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOT_VERSION = 5


def _owned_workspace(workspace_id: int, user: User, db: Session):
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == user.id,
        )
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _validate_snapshot(data: dict, expected_bytes: int):
    version = data.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise HTTPException(status_code=422, detail="Snapshot version must be a positive integer.")
    if version > MAX_SNAPSHOT_VERSION:
        raise HTTPException(
            status_code=422,
            detail=f"Snapshot version {version} is not supported by this API (maximum {MAX_SNAPSHOT_VERSION}).",
        )
    for field, expected_type, description in (
        ("workspace", dict, "an object"),
        ("files", list, "a list"),
        ("browser_urls", list, "a list"),
    ):
        if field in data and not isinstance(data[field], expected_type):
            raise HTTPException(status_code=422, detail=f"Snapshot field '{field}' must be {description}.")
    if "application" in data and not isinstance(data["application"], str):
        raise HTTPException(status_code=422, detail="Snapshot application must be a string.")

    # The client's whole-payload digest covers the exact UTF-8 JSON bytes.
    if expected_bytes <= 0 or expected_bytes > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Snapshot exceeds the 256 MiB upload limit.")

    integrity = data.get("_integrity")
    if integrity is not None:
        if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
            raise HTTPException(status_code=422, detail="Snapshot integrity metadata is invalid.")
        expected_digest = integrity.get("digest")
        unsigned = dict(data)
        unsigned.pop("_integrity", None)
        canonical = json.dumps(
            unsigned, separators=(",", ":"), ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        actual_digest = hashlib.sha256(canonical).hexdigest()
        if not isinstance(expected_digest, str) or not hmac.compare_digest(expected_digest, actual_digest):
            raise HTTPException(status_code=422, detail="Snapshot integrity check failed.")


@router.post("/{workspace_id}/snapshot-uploads")
def begin_snapshot_upload(
    workspace_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_workspace(workspace_id, current_user, db)
    # CHANGED: Reclaim abandoned uploads and old completion receipts.
    expired_before = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
    db.execute(
        delete(SnapshotUpload).where(SnapshotUpload.created_at < expired_before)
    )
    db.commit()
    total_bytes = data.get("total_bytes")
    chunk_count = data.get("chunk_count")
    digest = data.get("sha256")
    if isinstance(total_bytes, bool) or not isinstance(total_bytes, int) or not 1 <= total_bytes <= MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload size must be between 1 byte and 256 MiB.")
    expected_chunks = (total_bytes + CHUNK_BYTES - 1) // CHUNK_BYTES
    if isinstance(chunk_count, bool) or not isinstance(chunk_count, int) or chunk_count != expected_chunks:
        raise HTTPException(status_code=422, detail="Chunk count does not match the declared upload size.")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise HTTPException(status_code=422, detail="A lowercase SHA-256 upload digest is required.")

    upload = SnapshotUpload(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        user_id=current_user.id,
        chunk_count=chunk_count,
        total_bytes=total_bytes,
        sha256=digest,
    )
    db.add(upload)
    db.commit()
    return {
        "upload_id": upload.id,
        "chunk_bytes": CHUNK_BYTES,
        "chunk_count": chunk_count,
        "total_bytes": total_bytes,
    }


@router.put("/{workspace_id}/snapshot-uploads/{upload_id}/chunks/{chunk_index}")
def put_snapshot_chunk(
    workspace_id: int,
    upload_id: str,
    chunk_index: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_workspace(workspace_id, current_user, db)
    upload = db.scalar(
        select(SnapshotUpload).where(
            SnapshotUpload.id == upload_id,
            SnapshotUpload.workspace_id == workspace_id,
            SnapshotUpload.user_id == current_user.id,
        )
    )
    if upload is None:
        raise HTTPException(status_code=404, detail="Snapshot upload not found or expired.")
    if isinstance(chunk_index, bool) or not 0 <= chunk_index < upload.chunk_count:
        raise HTTPException(status_code=422, detail="Chunk index is out of range.")

    encoded = data.get("data")
    supplied_digest = data.get("sha256")
    if not isinstance(encoded, str) or not isinstance(supplied_digest, str):
        raise HTTPException(status_code=422, detail="Chunk data and SHA-256 are required.")
    try:
        chunk = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error):
        raise HTTPException(status_code=422, detail="Chunk data is not valid base64.")
    expected_size = min(CHUNK_BYTES, upload.total_bytes - chunk_index * CHUNK_BYTES)
    if len(chunk) != expected_size:
        raise HTTPException(status_code=422, detail="Chunk size does not match the upload manifest.")
    actual_digest = hashlib.sha256(chunk).hexdigest()
    if not hmac.compare_digest(supplied_digest, actual_digest):
        raise HTTPException(status_code=422, detail="Chunk checksum verification failed.")

    existing = db.scalar(
        select(SnapshotUploadChunk).where(
            SnapshotUploadChunk.upload_id == upload_id,
            SnapshotUploadChunk.chunk_index == chunk_index,
        )
    )
    if existing is not None:
        if existing.sha256 != actual_digest:
            raise HTTPException(status_code=409, detail="A different chunk already occupies this index.")
        return {"uploaded": True, "chunk_index": chunk_index, "already_present": True}

    db.add(SnapshotUploadChunk(
        upload_id=upload_id,
        chunk_index=chunk_index,
        sha256=actual_digest,
        data=chunk,
    ))
    db.commit()
    return {"uploaded": True, "chunk_index": chunk_index, "already_present": False}


@router.post("/{workspace_id}/snapshot-uploads/{upload_id}/finalize")
def finalize_snapshot_upload(
    workspace_id: int,
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_workspace(workspace_id, current_user, db)
    upload = db.scalar(
        select(SnapshotUpload).where(
            SnapshotUpload.id == upload_id,
            SnapshotUpload.workspace_id == workspace_id,
            SnapshotUpload.user_id == current_user.id,
        )
    )
    if upload is None:
        raise HTTPException(status_code=404, detail="Snapshot upload not found or already finalized.")

    # CHANGED: Finalize is idempotent if the response to a previous finalize
    # was lost after the database committed the snapshot.
    if upload.snapshot_id is not None:
        saved = db.get(Snapshot, upload.snapshot_id)
        if saved is not None:
            number = db.scalar(
                select(func.count(Snapshot.id)).where(
                    Snapshot.workspace_id == workspace_id,
                    Snapshot.id <= saved.id,
                )
            ) or 1
            return {
                "id": saved.id,
                "workspace_id": saved.workspace_id,
                "snapshot_number": number,
                "version": saved.version,
                "created_at": saved.created_at,
                "uploaded_bytes": upload.total_bytes,
                "verified": True,
                "already_finalized": True,
            }

    chunks = db.scalars(
        select(SnapshotUploadChunk)
        .where(SnapshotUploadChunk.upload_id == upload_id)
        .order_by(SnapshotUploadChunk.chunk_index)
    ).all()
    if len(chunks) != upload.chunk_count or [item.chunk_index for item in chunks] != list(range(upload.chunk_count)):
        raise HTTPException(status_code=409, detail="Upload is incomplete. No snapshot was created.")

    raw = b"".join(item.data for item in chunks)
    if len(raw) != upload.total_bytes:
        raise HTTPException(status_code=422, detail="Uploaded byte count does not match the manifest.")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), upload.sha256):
        raise HTTPException(status_code=422, detail="Full snapshot checksum verification failed.")
    try:
        snapshot_data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Uploaded snapshot is not valid UTF-8 JSON.")
    if not isinstance(snapshot_data, dict):
        raise HTTPException(status_code=422, detail="Snapshot payload must be a JSON object.")
    _validate_snapshot(snapshot_data, len(raw))

    snapshot = Snapshot(
        workspace_id=workspace_id,
        version=snapshot_data.get("version", 1),
        data=snapshot_data,
    )
    db.add(snapshot)
    db.flush()
    snapshot_number = db.scalar(
        select(func.count(Snapshot.id)).where(
            Snapshot.workspace_id == workspace_id,
            Snapshot.id <= snapshot.id,
        )
    ) or 1
    # CHANGED: Retain the upload receipt for idempotent finalize retries,
    # but discard staged bytes once the complete snapshot has been committed.
    upload.snapshot_id = snapshot.id
    db.execute(
        delete(SnapshotUploadChunk).where(
            SnapshotUploadChunk.upload_id == upload_id
        )
    )
    db.commit()
    db.refresh(snapshot)
    return {
        "id": snapshot.id,
        "workspace_id": snapshot.workspace_id,
        "snapshot_number": snapshot_number,
        "version": snapshot.version,
        "created_at": snapshot.created_at,
        "uploaded_bytes": len(raw),
        "verified": True,
    }


@router.delete("/{workspace_id}/snapshot-uploads/{upload_id}")
def cancel_snapshot_upload(
    workspace_id: int,
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _owned_workspace(workspace_id, current_user, db)
    upload = db.scalar(
        select(SnapshotUpload).where(
            SnapshotUpload.id == upload_id,
            SnapshotUpload.workspace_id == workspace_id,
            SnapshotUpload.user_id == current_user.id,
        )
    )
    if upload is not None:
        if upload.snapshot_id is not None:
            return {"cancelled": False, "finalized": True, "snapshot_id": upload.snapshot_id}
        db.delete(upload)
        db.commit()
    return {"cancelled": True}


@router.get("/{workspace_id}/snapshots/{snapshot_id}/download-manifest")
def snapshot_download_manifest(
    workspace_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Describe a snapshot download without returning its potentially huge body."""
    _owned_workspace(workspace_id, current_user, db)
    snapshot = db.scalar(
        select(Snapshot).where(
            Snapshot.id == snapshot_id,
            Snapshot.workspace_id == workspace_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    raw = json.dumps(
        snapshot.data, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="This saved snapshot exceeds the current 256 MiB download limit.",
        )
    return {
        "snapshot_id": snapshot.id,
        "total_bytes": len(raw),
        "chunk_bytes": CHUNK_BYTES,
        "chunk_count": (len(raw) + CHUNK_BYTES - 1) // CHUNK_BYTES,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


@router.get("/{workspace_id}/snapshots/{snapshot_id}/download-chunks/{chunk_index}")
def snapshot_download_chunk(
    workspace_id: int,
    snapshot_id: int,
    chunk_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return one bounded, checksummed chunk of a stored snapshot."""
    _owned_workspace(workspace_id, current_user, db)
    snapshot = db.scalar(
        select(Snapshot).where(
            Snapshot.id == snapshot_id,
            Snapshot.workspace_id == workspace_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    raw = json.dumps(
        snapshot.data, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Snapshot exceeds the download size limit.")
    chunk_count = (len(raw) + CHUNK_BYTES - 1) // CHUNK_BYTES
    if isinstance(chunk_index, bool) or not 0 <= chunk_index < chunk_count:
        raise HTTPException(status_code=422, detail="Download chunk index is out of range.")
    start = chunk_index * CHUNK_BYTES
    chunk = raw[start:start + CHUNK_BYTES]
    return {
        "snapshot_id": snapshot.id,
        "chunk_index": chunk_index,
        "sha256": hashlib.sha256(chunk).hexdigest(),
        "data": base64.b64encode(chunk).decode("ascii"),
    }
