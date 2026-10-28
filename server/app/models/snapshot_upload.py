"""Resumable, chunked snapshot upload staging tables.

Chunks are persisted separately so each HTTP request stays small. An upload is
not visible as a snapshot until the final payload is verified and committed.
"""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from server.app.database import Base


class SnapshotUpload(Base):
    __tablename__ = "snapshot_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # CHANGED: Keep a completion receipt so a lost finalize response is safe to retry.
    snapshot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("snapshots.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )


class SnapshotUploadChunk(Base):
    __tablename__ = "snapshot_upload_chunks"
    __table_args__ = (
        UniqueConstraint("upload_id", "chunk_index", name="uq_snapshot_upload_chunk"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_id: Mapped[str] = mapped_column(
        ForeignKey("snapshot_uploads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
