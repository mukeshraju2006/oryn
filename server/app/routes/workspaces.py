from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy import select
from sqlalchemy.orm import Session

from server.app.database import get_db
from server.app.models.user import User
from server.app.models.workspace import Workspace

# CHANGED: Authentication dependency
from server.app.routes.auth import (
    get_current_user,
)


router = APIRouter(
    prefix="/workspaces",
    tags=["workspaces"],
)


@router.post("/")
def create_workspace(
    data: dict,
    db: Session = Depends(get_db),

    # CHANGED:
    # User comes from JWT instead of request body.
    current_user: User = Depends(
        get_current_user
    ),
):

    name = data.get("name")

    if not name:
        raise HTTPException(
            status_code=400,
            detail="name is required",
        )

    workspace = Workspace(
        # CHANGED:
        # Never trust user_id supplied by client.
        user_id=current_user.id,
        name=name,
    )

    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    return {
        "id": workspace.id,
        "user_id": workspace.user_id,
        "name": workspace.name,
        "created_at": workspace.created_at,
    }


@router.get("/")
def list_workspaces(
    db: Session = Depends(get_db),

    # CHANGED:
    # Only return authenticated user's workspaces.
    current_user: User = Depends(
        get_current_user
    ),
):

    workspaces = db.scalars(
        select(Workspace)
        .where(
            Workspace.user_id
            == current_user.id
        )
        .order_by(
            Workspace.created_at.desc()
        )
    ).all()

    return [
        {
            "id": workspace.id,
            "user_id": workspace.user_id,
            "name": workspace.name,
            "created_at": workspace.created_at,
            "updated_at": workspace.updated_at,
        }
        for workspace in workspaces
    ]


def get_owned_workspace(workspace_id: int, current_user: User, db: Session):
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == current_user.id,
        )
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.patch("/{workspace_id}")
def rename_workspace(
    workspace_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=422, detail="Workspace name cannot be empty.")
    if len(name.strip()) > 255:
        raise HTTPException(status_code=422, detail="Workspace name must be 255 characters or fewer.")
    workspace.name = name.strip()
    db.commit()
    db.refresh(workspace)
    return {"id": workspace.id, "name": workspace.name, "updated_at": workspace.updated_at}


@router.delete("/{workspace_id}")
def delete_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = get_owned_workspace(workspace_id, current_user, db)
    # Explicitly delete dependent snapshots first; the existing schema does
    # not declare ON DELETE CASCADE and we must not rely on database defaults.
    from server.app.models.snapshot import Snapshot
    db.query(Snapshot).filter(Snapshot.workspace_id == workspace_id).delete(
        synchronize_session=False
    )
    db.delete(workspace)
    db.commit()
    return {"deleted": True, "workspace_id": workspace_id}
