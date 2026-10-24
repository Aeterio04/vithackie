"""Kawach GitHub Fix Pipeline.

Autonomous LangGraph pipeline verifying Playwright test failures, extracting
commit context from origin/main, synthesizing search-and-replace patches via LLM,
and creating pull requests.
"""

from kawach_fix.deps import Deps
from kawach_fix.graph import arun_fix_pipeline, run_fix_pipeline
from kawach_fix.schemas import (
    CommitContext,
    CommitSummary,
    ErrorReport,
    FileEdit,
    FilePatch,
    FixOptions,
    FixProposal,
    FixRequest,
    FixResult,
    FixStatus,
    PullRequestInfo,
    RunItem,
    SkippedFile,
    VerificationResult,
)

__all__ = [
    "run_fix_pipeline",
    "arun_fix_pipeline",
    "Deps",
    "FixRequest",
    "FixOptions",
    "ErrorReport",
    "RunItem",
    "VerificationResult",
    "FilePatch",
    "SkippedFile",
    "CommitContext",
    "CommitSummary",
    "FileEdit",
    "FixProposal",
    "PullRequestInfo",
    "FixResult",
    "FixStatus",
]
