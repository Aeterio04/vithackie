# SCAFFOLD: not implemented
"""Pydantic wire models for commit triggers, failure localization, and fix suggestions.

Scaffolded schemas supporting Section 8 / Appendix A product flow.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CommitEventCreate(BaseModel):
    """Payload representing a push or PR commit event from GitHub."""

    model_config = ConfigDict(extra="ignore")

    sha: str = Field(description="Git commit SHA-1 or SHA-256")
    branch: str = Field(description="Target branch name")
    author: Optional[str] = Field(default=None, description="Commit author name or handle")
    message: Optional[str] = Field(default=None, description="Commit commit message")
    pushed_at: datetime = Field(description="Timestamp of push")
    webhook_delivery_id: str = Field(description="Unique GitHub webhook delivery ID for idempotency")
    files_changed: List[str] = Field(default_factory=list, description="List of files touched by commit")
    diff_stats: Dict[str, Any] = Field(default_factory=dict, description="Additions, deletions, total lines")


class CommitEventRead(BaseModel):
    """Commit event model returned to clients."""

    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    provider: str = "github"
    sha: str
    branch: str
    author: Optional[str] = None
    message: Optional[str] = None
    pushed_at: datetime
    webhook_delivery_id: str
    files_changed: List[str] = Field(default_factory=list)
    diff_stats: Dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime


class FailureCandidateRead(BaseModel):
    """Ranked probabilistic candidate source file responsible for a test failure."""

    model_config = ConfigDict(extra="ignore")

    id: str
    rank: int = Field(description="Rank order (1 = most likely)")
    file_path: str = Field(description="Target repository file path")
    component: Optional[str] = Field(default=None, description="Detected component name")
    confidence: float = Field(ge=0.0, le=1.0, description="Probabilistic confidence score")
    rationale: Optional[str] = Field(default=None, description="Analysis justification")


class FailureAnalysisRead(BaseModel):
    """Failure localization report mapping regression failure back to code."""

    model_config = ConfigDict(extra="ignore")

    id: str
    run_id: str
    test_result_id: str
    commit_event_id: Optional[str] = None
    summary: Optional[str] = None
    status: str
    candidates: List[FailureCandidateRead] = Field(default_factory=list)
    created_at: datetime


class FixSuggestionRead(BaseModel):
    """Proposed code patch or auto-fix suggestion."""

    model_config = ConfigDict(extra="ignore")

    id: str
    analysis_id: str
    diff_artifact_id: Optional[str] = None
    risk_class: str = "small"  # small | large
    files_changed: int = 1
    lines_changed: int = 0
    status: str = "proposed"  # proposed | accepted | rejected | applied | validated
    validation_verification_id: Optional[str] = None
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class FixSuggestionActionRequest(BaseModel):
    """Action taken on a fix suggestion (accept, reject, auto-fix PR)."""

    model_config = ConfigDict(extra="ignore")

    action: str = Field(description="accept | reject | create_pr")
