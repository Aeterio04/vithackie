"""Artifact metadata model representing stored files, evidence, traces, and reports."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kawach.db.base import Base, generate_uuid, utc_now


class Artifact(Base):
    """Metadata record for a physical file persisted in the artifact store."""

    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_project_kind", "project_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("runs.id", ondelete="SET NULL"), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # screenshot|video|trace|console|network|script|report|diff|other
    uri: Mapped[str] = mapped_column(String(1024), nullable=False)  # relative path under artifact root
    mime: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
