"""Run lifecycle, execution stages, application maps, metrics, and LLM telemetry models."""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
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


class Run(Base, TimestampMixin):
    """Core test execution run entity."""

    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_project_created_desc", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Supports run_id like 20261022-220551-3fa1
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)  # manual|commit|schedule|regression
    commit_event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    parent_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)  # manual|autonomous
    stage: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    spec_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_golden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project")
    stage_times: Mapped[list["RunStageTime"]] = relationship("RunStageTime", back_populates="run", cascade="all, delete-orphan")
    app_map: Mapped[Optional["AppMap"]] = relationship("AppMap", back_populates="run", uselist=False, cascade="all, delete-orphan")
    metrics: Mapped[Optional["RunMetric"]] = relationship("RunMetric", back_populates="run", uselist=False, cascade="all, delete-orphan")
    llm_usage_records: Mapped[list["LlmUsage"]] = relationship("LlmUsage", back_populates="run", cascade="all, delete-orphan")


class RunStageTime(Base):
    """Timing checkpoints for each pipeline execution stage."""

    __tablename__ = "run_stage_times"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    run: Mapped["Run"] = relationship("Run", back_populates="stage_times")


class AppMap(Base):
    """Explored application map topology snapshot."""

    __tablename__ = "app_maps"

    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    pages_visited: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    budget_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    run: Mapped["Run"] = relationship("Run", back_populates="app_map")


class RunMetric(Base):
    """Aggregated run coverage, execution times, and bug counts snapshot."""

    __tablename__ = "run_metrics"

    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    wall_clock_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    run: Mapped["Run"] = relationship("Run", back_populates="metrics")


class LlmUsage(Base):
    """Fine-grained token counting and financial tracking per agent invocation."""

    __tablename__ = "llm_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    run: Mapped["Run"] = relationship("Run", back_populates="llm_usage_records")
