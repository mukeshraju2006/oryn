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