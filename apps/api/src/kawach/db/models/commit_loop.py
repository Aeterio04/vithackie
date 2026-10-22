"""Commit triggers, root cause localization, and auto-fix suggestions models (Scaffolded schema per Section 6)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kawach.db.base import Base, TimestampMixin, generate_uuid, utc_now


class CommitEvent(Base):
    """Git commit push event received via GitHub webhook."""

    __tablename__ = "commit_events"
    __table_args__ = (
        Index("ix_commit_events_project_pushed_desc", "project_id", "pushed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="github", nullable=False)
    sha: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    branch: Mapped[str] = mapped_column(String(128), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pushed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    webhook_delivery_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    files_changed: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    diff_stats: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class FailureAnalysis(Base):
    """Probabilistic failure localization mapping a test error back to commit diffs."""

    __tablename__ = "failure_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    test_result_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    commit_event_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("commit_events.id", ondelete="SET NULL"), index=True, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    candidates: Mapped[list["FailureCandidate"]] = relationship("FailureCandidate", back_populates="analysis", cascade="all, delete-orphan")
    fix_suggestions: Mapped[list["FixSuggestion"]] = relationship("FixSuggestion", back_populates="analysis", cascade="all, delete-orphan")


class FailureCandidate(Base):
    """Ranked probabilistic candidate source file or component responsible for failure."""

    __tablename__ = "failure_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("failure_analyses.id", ondelete="CASCADE"), index=True, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    component: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0 to 1.0
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    analysis: Mapped["FailureAnalysis"] = relationship("FailureAnalysis", back_populates="candidates")


class FixSuggestion(Base, TimestampMixin):
    """Proposed code patch / diff suggestion to remediate a verified regression."""

    __tablename__ = "fix_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("failure_analyses.id", ondelete="CASCADE"), index=True, nullable=False)
    diff_artifact_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    risk_class: Mapped[str] = mapped_column(String(32), default="small", nullable=False)  # small|large
    files_changed: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lines_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="proposed", nullable=False)  # proposed|accepted|rejected|applied|validated
    validation_verification_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    pr_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    pr_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    analysis: Mapped["FailureAnalysis"] = relationship("FailureAnalysis", back_populates="fix_suggestions")
