from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from server.app.database import Base


class Snapshot(Base):

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    # CHANGED: Preserve the exact verified upload bytes. Re-serializing a large
    # JSON document for every 512 KiB download request is needlessly expensive.
    raw_payload: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )