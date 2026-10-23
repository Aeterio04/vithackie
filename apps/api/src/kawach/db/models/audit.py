"""Audit logging entity for compliance and security tracking."""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from kawach.db.base import Base, generate_uuid, utc_now


class AuditLog(Base):
    """Immutable audit trail of security-sensitive operations."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_user_action", "user_id", "action"),
        Index("ix_audit_project_action", "project_id", "action"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # login|credential_change|integration_change|run_start|export
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)  # user|project|run|export
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    client_type: Mapped[str] = mapped_column(String(20), default="web", nullable=False)  # web|github|mcp
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # Supports IPv4 and IPv6
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
