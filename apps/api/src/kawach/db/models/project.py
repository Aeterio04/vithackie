"""Project models — the home of all test runs, specs, credentials, and integrations."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kawach.db.base import Base, TimestampMixin, generate_uuid, utc_now


class Project(Base, TimestampMixin):
    """Project entity representing an application under test."""

    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_owner_archived", "owner_id", "archived_at"),
        UniqueConstraint("owner_id", "slug", name="uq_projects_owner_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    workspace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    target_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    github_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    pat_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_mode: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    budgets: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    allowed_hosts: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    spec_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def user_id(self) -> str:
        return self.owner_id

    @user_id.setter
    def user_id(self, val: str) -> None:
        self.owner_id = val

    @property
    def test_url(self) -> str:
        return self.target_url

    @test_url.setter
    def test_url(self, val: str) -> None:
        self.target_url = val

    # Relationships
    owner: Mapped["User"] = relationship("User")
    spec_items: Mapped[list["SpecItem"]] = relationship("SpecItem", back_populates="project", cascade="all, delete-orphan")
    credentials: Mapped[Optional["ProjectCredential"]] = relationship("ProjectCredential", back_populates="project", uselist=False, cascade="all, delete-orphan")
    integrations: Mapped[list["ProjectIntegration"]] = relationship("ProjectIntegration", back_populates="project", cascade="all, delete-orphan")


class SpecItem(Base):
    """Individual parsed specification requirement linked to tests and coverage."""

    __tablename__ = "spec_items"
    __table_args__ = (
        UniqueConstraint("project_id", "spec_version", "key", name="uq_spec_items_project_version_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    spec_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    key: Mapped[str] = mapped_column(String(32), nullable=False)  # S1, S2...
    text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="spec_items")


class ProjectCredential(Base):
    """Encrypted project credentials for authenticating against target applications."""

    __tablename__ = "project_credentials"

    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet encrypted
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="credentials")


class ProjectIntegration(Base, TimestampMixin):
    """External integrations (e.g. GitHub repository connection and webhooks)."""

    __tablename__ = "project_integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="github", nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), default="main", nullable=False)
    token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted fine-grained GitHub token
    webhook_secret_ciphertext: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    token_scopes: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="integrations")
