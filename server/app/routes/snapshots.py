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

    # IDs are global database identifiers; display numbers belong to users.
    snapshot_number = db.scalar(
        select(func.count(Snapshot.id))
        .join(Workspace, Snapshot.workspace_id == Workspace.id)
        .where(
            Workspace.user_id == current_user.id,
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

    # Number snapshots across all workspaces owned by this user. The
    # window function avoids loading every snapshot into application memory.
    numbered_ids = (
        select(
            Snapshot.id.label("snapshot_id"),
            func.row_number().over(order_by=Snapshot.id).label("snapshot_number"),
        )
        .join(Workspace, Snapshot.workspace_id == Workspace.id)
        .where(Workspace.user_id == current_user.id)
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