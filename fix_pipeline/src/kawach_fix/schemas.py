"""Pydantic schemas for Kawach GitHub Fix Pipeline.

Strict models validating every handoff between LangGraph nodes.
Guarantees:
- Secrets (e.g. github_pat) are stored as SecretStr and never serialized into FixResult.
- base_branch is fixed to 'main'.
- repo string can be 'owner/repo' or a full GitHub URL.
"""

from __future__ import annotations

import re
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


def normalize_github_repo(repo_str: str) -> str:
    """Normalize owner/repo format from plain string, SSH, or HTTPS URL."""
    val = repo_str.strip()
    # Match https://github.com/owner/repo or http://...
    m = re.search(r"github\.com[/:]([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git|/)?$", val)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    # Match standard owner/repo
    if re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", val):
        return val
    raise ValueError(f"Invalid GitHub repository identifier '{repo_str}'. Expected 'owner/repo' or GitHub URL.")


class FixOptions(BaseModel):
    """Execution options and safety bounds for the pipeline."""

    model_config = ConfigDict(extra="forbid")

    verify_runs: int = Field(default=3, ge=1, le=10, description="Total replay runs to verify test defect.")
    min_failures: int = Field(default=2, ge=1, le=10, description="Minimum failures to classify as confirmed defect.")
    dry_run: bool = Field(default=False, description="When true, computes fix and PR payload but skips write operations.")
    draft_pr: bool = Field(default=False, description="Whether the created pull request should be in draft state.")
    max_files: int = Field(default=15, ge=1, le=50, description="Maximum files from commit to inspect.")
    max_file_bytes: int = Field(default=100_000, ge=1000, le=2_000_000, description="Max byte size per file to fetch.")
    max_patch_chars: int = Field(default=20_000, ge=500, le=200_000, description="Max characters in patch diff before truncation.")
    run_timeout_sec: int = Field(default=30, ge=5, le=300, description="Subprocess timeout per test execution run.")

    @model_validator(mode="after")
    def validate_failure_bounds(self) -> FixOptions:
        if self.min_failures > self.verify_runs:
            raise ValueError(f"min_failures ({self.min_failures}) cannot be greater than verify_runs ({self.verify_runs})")
        return self


class ErrorReport(BaseModel):
    """Details of the test failure observed in the test suite."""

    model_config = ConfigDict(extra="forbid")

    test_name: str = Field(..., min_length=1)
    failing_step: Optional[str] = None
    message: str = Field(..., min_length=1)
    console: List[str] = Field(default_factory=list)
    network: List[str] = Field(default_factory=list)


class FixRequest(BaseModel):
    """Input request specification for the fix pipeline."""

    model_config = ConfigDict(extra="forbid")

    repo: str = Field(..., description="Target repo in 'owner/name' format or GitHub URL.")
    github_pat: SecretStr = Field(..., description="Fine-grained or classic GitHub Personal Access Token.")
    base_branch: Literal["main"] = Field(default="main", description="Only 'main' is permitted.")
    error: ErrorReport
    playwright_script: str = Field(..., min_length=1, description="Path to .spec.ts or raw script code.")
    target_url: str = Field(..., min_length=1, description="Base URL of running target application.")
    playwright_project_dir: str = Field(..., min_length=1, description="Directory containing playwright runner config.")
    options: FixOptions = Field(default_factory=FixOptions)
    run_id: Optional[str] = Field(default=None, description="Unique trace/run identifier.")

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, v: str) -> str:
        return normalize_github_repo(v)

    @field_validator("base_branch")
    @classmethod
    def validate_base_branch(cls, v: str) -> str:
        if v != "main":
            raise ValueError(f"Only base_branch='main' is supported. Received '{v}'.")
        return v


class RunItem(BaseModel):
    """Record of a single replay test execution."""

    model_config = ConfigDict(extra="forbid")

    index: int
    passed: bool
    error_text: Optional[str] = None
    duration_ms: int = Field(ge=0)


class VerificationResult(BaseModel):
    """Output from VerifierAgent."""

    model_config = ConfigDict(extra="forbid")

    runs: List[RunItem]
    failures: int = Field(ge=0)
    verdict: Literal["confirmed", "flaky", "not_reproduced"]
    observed_error: Optional[str] = None


class FilePatch(BaseModel):
    """Details and content of a file touched by the latest commit on main."""

    model_config = ConfigDict(extra="forbid")

    path: str
    status: str
    patch: Optional[str] = None
    content_at_sha: Optional[str] = None
    blob_sha: Optional[str] = None
    truncated: bool = False


class SkippedFile(BaseModel):
    """Record of a touched file that was excluded from LLM context."""

    model_config = ConfigDict(extra="forbid")

    path: str
    reason: str


class CommitContext(BaseModel):
    """Pinned latest commit on origin/main."""

    model_config = ConfigDict(extra="forbid")

    sha: str = Field(..., min_length=7)
    message: str
    author: str
    files: List[FilePatch] = Field(default_factory=list)
    skipped: List[SkippedFile] = Field(default_factory=list)


class FileEdit(BaseModel):
    """Exact search-and-replace edit block."""

    model_config = ConfigDict(extra="forbid")

    path: str
    old_str: str
    new_str: str


class FixProposal(BaseModel):
    """Defect repair proposal generated by the LLM."""

    model_config = ConfigDict(extra="forbid")

    can_fix: bool
    confidence: float = Field(ge=0.0, le=1.0)
    root_cause: str
    explanation: str
    edits: List[FileEdit] = Field(default_factory=list)
    pr_title: str
    pr_summary: str


class PullRequestInfo(BaseModel):
    """Metadata regarding the opened or existing pull request."""

    model_config = ConfigDict(extra="forbid")

    number: Optional[int] = None
    url: Optional[str] = None
    branch: str
    created: bool


class CommitSummary(BaseModel):
    """Safe, high-level summary of the inspected commit."""

    model_config = ConfigDict(extra="forbid")

    sha: str
    message: str
    files: List[str]


FixStatus = Literal[
    "not_reproduced",
    "flaky",
    "no_editable_changes",
    "fix_not_possible",
    "invalid_llm_output",
    "github_error",
    "pr_opened",
    "pr_exists",
    "dry_run_ready",
]


class FixResult(BaseModel):
    """Final, unredacted result object returned by the fix pipeline.

    Must NEVER contain credentials, secret tokens, or full PATs.
    """

    model_config = ConfigDict(extra="forbid")

    status: FixStatus
    reason: str
    verification: Optional[VerificationResult] = None
    commit: Optional[CommitSummary] = None
    proposal: Optional[FixProposal] = None
    pull_request: Optional[PullRequestInfo] = None
