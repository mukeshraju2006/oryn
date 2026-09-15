from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()
from server.app.database import (
    Base,
    engine,
)
from server.app.models import (
    User,
    Workspace,
    Snapshot,
)

from server.app.routes.workspaces import (
    router as workspace_router,
)

from server.app.routes.snapshots import (
    router as snapshot_router,
)

# CHANGED: Authentication router
from server.app.routes.auth import (
    router as auth_router,
)


app = FastAPI(
    title="Oryn Cloud",
    version="0.1.0",
)


Base.metadata.create_all(
    bind=engine
)


app.include_router(
    workspace_router
)

app.include_router(
    snapshot_router
)

# CHANGED: Register authentication routes
app.include_router(
    auth_router
)


@app.get("/")
def root():

    return {
        "name": "Oryn Cloud",
        "status": "running",
    }