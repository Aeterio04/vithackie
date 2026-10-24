"""Artifact metadata model representing stored files, evidence, traces, and reports."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kawach.db.base import Base, generate_uuid, utc_now


class Artifact(Base):
    """Metadata record for a physical file persisted in the artifact store."""

    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_project_kind", "project_id", "kind"),
        Index("ix_artifacts_user_type", "user_id", "type"),
    )

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Ownership & hierarchy
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    test_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("runs.id", ondelete="SET NULL"), index=True, nullable=True)

    # File metadata
    type: Mapped[str] = mapped_column(String(32), default="other", nullable=False)  # screenshot|recording|other
    kind: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # screenshot|video|trace|console|network|script|report|diff|other
    relative_path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)  # relative to base storage
    uri: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)  # backwards-compatible URI
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mime: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    def __init__(self, **kwargs: Any) -> None:
        # Synchronize type <-> kind
        if "type" in kwargs and "kind" not in kwargs:
            kwargs["kind"] = kwargs["type"]
        elif "kind" in kwargs and "type" not in kwargs:
            kwargs["type"] = kwargs["kind"]

        # Synchronize relative_path <-> uri
        if "relative_path" in kwargs and "uri" not in kwargs:
            kwargs["uri"] = kwargs["relative_path"]
        elif "uri" in kwargs and "relative_path" not in kwargs:
            kwargs["relative_path"] = kwargs["uri"]

        # Synchronize size <-> size_bytes
        if "size" in kwargs and "size_bytes" not in kwargs:
            kwargs["size_bytes"] = kwargs["size"]
        elif "size_bytes" in kwargs and "size" not in kwargs:
            kwargs["size"] = kwargs["size_bytes"]

        # Synchronize mime_type <-> mime
        if "mime_type" in kwargs and "mime" not in kwargs:
            kwargs["mime"] = kwargs["mime_type"]
        elif "mime" in kwargs and "mime_type" not in kwargs:
            kwargs["mime_type"] = kwargs["mime"]

        # Synchronize test_id <-> run_id
        if "test_id" in kwargs and "run_id" not in kwargs:
            kwargs["run_id"] = kwargs["test_id"]
        elif "run_id" in kwargs and "test_id" not in kwargs:
            kwargs["test_id"] = kwargs["run_id"]

        super().__init__(**kwargs)
