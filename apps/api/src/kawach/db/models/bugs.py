"""Defects, evidence mappings, duplicates, and 3x deterministic replay verification models."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kawach.db.base import Base, TimestampMixin, generate_uuid, utc_now


class Bug(Base, TimestampMixin):
    """Triaged and verified software defect entity."""

    __tablename__ = "bugs"
    __table_args__ = (
        Index("ix_bugs_project_status", "project_id", "status"),
        Index("ix_bugs_fingerprint", "fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(32), nullable=False)  # B01, B02...
    test_case_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True)
    signature: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)  # Stable cross-run hash
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # functional|visual|console_error|network_error|security
    severity: Mapped[str] = mapped_column(String(32), nullable=False)  # critical|high|medium|low
    steps: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    expected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actual: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)  # candidate|confirmed|flaky|not_reproduced
    first_seen_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    evidence_records: Mapped[list["BugEvidence"]] = relationship("BugEvidence", back_populates="bug", cascade="all, delete-orphan")
    duplicates: Mapped[list["BugDuplicate"]] = relationship("BugDuplicate", back_populates="bug", cascade="all, delete-orphan")
    verifications: Mapped[list["Verification"]] = relationship("Verification", back_populates="bug", cascade="all, delete-orphan")


class BugEvidence(Base):
    """Link table between bugs and stored evidence artifacts."""

    __tablename__ = "bug_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    bug_id: Mapped[str] = mapped_column(String(36), ForeignKey("bugs.id", ondelete="CASCADE"), index=True, nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # screenshot|video|trace|console|network|other

    # Relationships
    bug: Mapped["Bug"] = relationship("Bug", back_populates="evidence_records")
    artifact: Mapped["Artifact"] = relationship("Artifact")


class BugDuplicate(Base):
    """Cross-test duplicates tracking for a single defect."""

    __tablename__ = "bug_duplicates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    bug_id: Mapped[str] = mapped_column(String(36), ForeignKey("bugs.id", ondelete="CASCADE"), index=True, nullable=False)
    duplicate_test_case_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    # Relationships
    bug: Mapped["Bug"] = relationship("Bug", back_populates="duplicates")


class Verification(Base):
    """Deterministic replay verification record (3 trials)."""

    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    bug_id: Mapped[str] = mapped_column(String(36), ForeignKey("bugs.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="bug", nullable=False)  # bug|fix_validation
    reproduced_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts_total: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # confirmed|flaky|not_reproduced
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    bug: Mapped["Bug"] = relationship("Bug", back_populates="verifications")
    attempts: Mapped[list["VerificationAttempt"]] = relationship("VerificationAttempt", back_populates="verification", cascade="all, delete-orphan")


class VerificationAttempt(Base):
    """Individual trial attempt in a 3x replay verification sequence."""

    __tablename__ = "verification_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    verification_id: Mapped[str] = mapped_column(String(36), ForeignKey("verifications.id", ondelete="CASCADE"), index=True, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    reproduced: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    verification: Mapped["Verification"] = relationship("Verification", back_populates="attempts")
