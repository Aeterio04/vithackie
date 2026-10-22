"""Test cases, spec mappings, synthesized scripts, review decisions, and test results models."""

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


class TestCase(Base, TimestampMixin):
    """Planned or ad-hoc test case entity."""

    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint("run_id", "key", name="uq_test_cases_run_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(32), nullable=False)  # T01, T02...
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="proposed", nullable=False)  # proposed|approved|rejected
    origin: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)  # planned|adhoc|saved
    steps: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    # Relationships
    spec_refs: Mapped[list["TestCaseSpecRef"]] = relationship("TestCaseSpecRef", back_populates="test_case", cascade="all, delete-orphan")
    scripts: Mapped[list["TestScript"]] = relationship("TestScript", back_populates="test_case", cascade="all, delete-orphan")


class TestCaseSpecRef(Base):
    """Many-to-many relationship mapping test cases to specification items."""

    __tablename__ = "test_case_spec_refs"
    __table_args__ = (
        UniqueConstraint("test_case_id", "spec_item_id", name="uq_test_spec_refs"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    spec_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("spec_items.id", ondelete="CASCADE"), index=True, nullable=False)

    # Relationships
    test_case: Mapped["TestCase"] = relationship("TestCase", back_populates="spec_refs")
    spec_item: Mapped["SpecItem"] = relationship("SpecItem")


class TestScript(Base):
    """Synthesized executable Playwright TypeScript code version."""

    __tablename__ = "test_scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    artifact_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # Pointer to artifact store
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ok", nullable=False)  # pending|ok|error
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    test_case: Mapped["TestCase"] = relationship("TestCase", back_populates="scripts")


class ReviewDecision(Base):
    """Audit log of human or autonomous agent catalog approval decisions."""

    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)  # approved|rejected
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer_kind: Mapped[str] = mapped_column(String(32), default="human", nullable=False)  # human|agent
    reviewer_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class TestResult(Base):
    """Execution outcome from runner worker for a single test case."""

    __tablename__ = "test_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    test_case_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("test_cases.id", ondelete="SET NULL"), index=True, nullable=True)
    saved_test_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)  # planned|exploratory|saved
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)  # passed|assertion_failure|test_error
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    worker: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # w1, w2
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
