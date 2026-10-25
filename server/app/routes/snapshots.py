import json

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server.app.database import get_db
from server.app.models.snapshot import Snapshot
from server.app.models.workspace import Workspace
from server.app.models.user import User

# CHANGED: Authentication dependency
from server.app.routes.auth import (
    get_current_user,
)


router = APIRouter(
    prefix="/workspaces",
    tags=["snapshots"],
)

MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_SNAPSHOT_VERSION = 5


# CHANGED:
# Verify that the workspace belongs to
# the authenticated user.
def get_user_workspace(
    workspace_id: int,
    current_user: User,
    db: Session,
):

    workspace = db.scalar(
        select(Workspace)
        .where(
            Workspace.id == workspace_id,
            Workspace.user_id
            == current_user.id,
        )
    )

    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    return workspace


@router.post(
    "/{workspace_id}/snapshots"
)
def create_snapshot(
    workspace_id: int,
    data: dict,
    db: Session = Depends(get_db),

    # CHANGED:
    current_user: User = Depends(
        get_current_user
    ),
):

    get_user_workspace(
        workspace_id,
        current_user,
        db,
    )

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
            raise HTTPException(
                status_code=422,
                detail=f"Snapshot field '{field}' must be {description}.",
            )
    if "application" in data and not isinstance(data["application"], str):
        raise HTTPException(status_code=422, detail="Snapshot application must be a string.")

    # Limit persisted snapshot size to protect the database from accidental
    # huge payloads and unbounded client uploads.
    payload_size = len(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    if payload_size > MAX_SNAPSHOT_BYTES:
        raise HTTPException(status_code=413, detail="Snapshot exceeds the 8 MiB limit.")

    snapshot = Snapshot(
        workspace_id=workspace_id,
        version=version,
        data=data,
    )

    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    # Display numbers are the ordinal position within this workspace's retained
    # history. Deletion/retention compacts the displayed sequence; the database ID
    # remains the stable identifier used by all actions.
    snapshot_number = db.scalar(
        select(func.count(Snapshot.id))
        .where(
            Snapshot.workspace_id == workspace_id,
            Snapshot.id <= snapshot.id,
        )
    ) or 1

    return {
        "id": snapshot.id,
        "workspace_id": snapshot.workspace_id,
        "snapshot_number": snapshot_number,
        "version": snapshot.version,
        "created_at": snapshot.created_at,
    }


@router.get(
    "/{workspace_id}/snapshots"
)
def list_snapshots(
    workspace_id: int,
    db: Session = Depends(get_db),

    # CHANGED:
    current_user: User = Depends(
        get_current_user
    ),
):

    get_user_workspace(
        workspace_id,
        current_user,
        db,
    )

    # Number snapshots independently inside the selected workspace. Keep the
    # numbering in SQL so large histories are not materialized in Python.
    numbered_ids = (
        select(
            Snapshot.id.label("snapshot_id"),
            func.row_number().over(order_by=Snapshot.id).label("snapshot_number"),
        )
        .where(Snapshot.workspace_id == workspace_id)
        .subquery()
    )

    numbered_snapshots = db.execute(
        select(Snapshot, numbered_ids.c.snapshot_number)
        .join(numbered_ids, Snapshot.id == numbered_ids.c.snapshot_id)
        .where(Snapshot.workspace_id == workspace_id)
        .order_by(Snapshot.id.desc())
    ).all()

    return [
        {
            "id": snapshot.id,
            "snapshot_number": snapshot_number,
            "version": snapshot.version,
            "created_at": snapshot.created_at,
            "application": (snapshot.data or {}).get("application", "workspace"),
            "file_count": len((snapshot.data or {}).get("files") or []),
            "browser_url_count": len((snapshot.data or {}).get("browser_urls") or []),
            "project_path": ((snapshot.data or {}).get("workspace") or {}).get("path", ""),
        }
        for snapshot, snapshot_number in numbered_snapshots
    ]


@router.get(
    "/{workspace_id}/snapshots/{snapshot_id}"
)
def get_snapshot(
    workspace_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),

    # CHANGED:
    current_user: User = Depends(
        get_current_user
    ),
):

    get_user_workspace(
        workspace_id,
        current_user,
        db,
    )

    snapshot = db.scalar(
        select(Snapshot)
        .where(
            Snapshot.id == snapshot_id,
            Snapshot.workspace_id
            == workspace_id,
        )
    )

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="Snapshot not found",
        )

    return snapshot.data


@router.delete("/{workspace_id}/snapshots/{snapshot_id}")
def delete_snapshot(
    workspace_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_user_workspace(workspace_id, current_user, db)
    snapshot = db.scalar(
        select(Snapshot).where(
            Snapshot.id == snapshot_id,
            Snapshot.workspace_id == workspace_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    db.delete(snapshot)
    db.commit()
    return {"deleted": True, "snapshot_id": snapshot_id}



@router.post("/{workspace_id}/snapshots/retention")
def prune_snapshots(
    workspace_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_user_workspace(workspace_id, current_user, db)
    keep_last = data.get("keep_last")
    if isinstance(keep_last, bool) or not isinstance(keep_last, int) or not 1 <= keep_last <= 5000:
        raise HTTPException(
            status_code=422,
            detail="keep_last must be an integer between 1 and 5000.",
        )
    older_ids = db.scalars(
        select(Snapshot.id)
        .where(Snapshot.workspace_id == workspace_id)
        .order_by(Snapshot.id.desc())
        .offset(keep_last)
    ).all()
    if older_ids:
        db.query(Snapshot).filter(Snapshot.id.in_(older_ids)).delete(
            synchronize_session=False
        )
        db.commit()
    return {"deleted_count": len(older_ids), "kept_count": min(keep_last, db.scalar(
        select(func.count(Snapshot.id)).where(Snapshot.workspace_id == workspace_id)
    ) or 0)}
