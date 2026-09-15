from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy import select
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

    snapshot = Snapshot(
        workspace_id=workspace_id,
        version=data.get(
            "version",
            1,
        ),
        data=data,
    )

    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    return {
        "id": snapshot.id,
        "workspace_id": snapshot.workspace_id,
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

    snapshots = db.scalars(
        select(Snapshot)
        .where(
            Snapshot.workspace_id
            == workspace_id
        )
        .order_by(
            Snapshot.created_at.desc()
        )
    ).all()

    return [
        {
            "id": snapshot.id,
            "version": snapshot.version,
            "created_at": snapshot.created_at,
        }
        for snapshot in snapshots
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