import gzip
import io

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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


@app.middleware("http")
async def decompress_snapshot_upload(request: Request, call_next):
    """Accept gzip-compressed snapshot JSON to reduce upload time on slow links."""
    if (
        request.method != "POST"
        or not request.url.path.endswith("/snapshots")
        or request.headers.get("content-encoding", "").lower() != "gzip"
    ):
        return await call_next(request)

    max_bytes = 8 * 1024 * 1024
    compressed = await request.body()
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            body = stream.read(max_bytes + 1)
    except (OSError, EOFError):
        return JSONResponse(
            {"detail": "Invalid gzip snapshot payload."},
            status_code=400,
        )

    if len(body) > max_bytes:
        return JSONResponse(
            {"detail": "Snapshot exceeds the 8 MiB limit."},
            status_code=413,
        )

    # Present decoded JSON to FastAPI exactly as if an uncompressed client
    # had sent it. Older clients remain compatible.
    request.scope["headers"] = [
        (name, value)
        for name, value in request.scope["headers"]
        if name.lower() not in (b"content-encoding", b"content-length")
    ]
    request.scope["headers"].append(
        (b"content-length", str(len(body)).encode("ascii"))
    )
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive
    return await call_next(request)


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