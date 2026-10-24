"""Saved regression test suite models (Scaffolded schema per Section 6)."""

from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kawach.db.base import Base, TimestampMixin, generate_uuid


class SavedTest(Base, TimestampMixin):
    """Pinned regression test living inside a project library."""

    __tablename__ = "saved_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    source_test_case_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    pinned_script_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    script_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="bug_repro", nullable=False)  # bug_repro|journey
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    last_result: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_run_at: Mapped[Optional[Any]] = mapped_column(String(64), nullable=True)

    @property
    def user_id(self) -> Optional[str]:
        return self.created_by

    @user_id.setter
    def user_id(self, val: Optional[str]) -> None:
        self.created_by = val

    @property
    def name(self) -> str:
        return self.title

    @name.setter
    def name(self, val: str) -> None:
        self.title = val

    # Relationships
    coverage: Mapped[list["SavedTestCoverage"]] = relationship("SavedTestCoverage", back_populates="saved_test", cascade="all, delete-orphan")


class SavedTestCoverage(Base):
    """Touchpoint mapping for diff-aware smart test selection."""

    __tablename__ = "saved_test_coverage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    saved_test_id: Mapped[str] = mapped_column(String(36), ForeignKey("saved_tests.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # page|component|file|route
    ref: Mapped[str] = mapped_column(String(512), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Relationships
    saved_test: Mapped["SavedTest"] = relationship("SavedTest", back_populates="coverage")


class RunSelectedTest(Base):
    """Link table documenting which saved tests were selected for a regression run."""

    __tablename__ = "run_selected_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    saved_test_id: Mapped[str] = mapped_column(String(36), ForeignKey("saved_tests.id", ondelete="CASCADE"), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), default="affected", nullable=False)  # affected|full|periodic
