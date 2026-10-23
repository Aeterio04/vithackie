"""Database models registry and package exports."""

from kawach.db.models.identity import User, RefreshToken, ApiToken
from kawach.db.models.project import Project, SpecItem, ProjectCredential, ProjectIntegration
from kawach.db.models.runs import Run, RunStageTime, AppMap, RunMetric, LlmUsage
from kawach.db.models.tests import TestCase, TestCaseSpecRef, TestScript, ReviewDecision, TestResult
from kawach.db.models.artifacts import Artifact
from kawach.db.models.bugs import Bug, BugEvidence, BugDuplicate, Verification, VerificationAttempt
from kawach.db.models.saved_tests import SavedTest, SavedTestCoverage, RunSelectedTest
from kawach.db.models.commit_loop import CommitEvent, FailureAnalysis, FailureCandidate, FixSuggestion
from kawach.db.models.audit import AuditLog

__all__ = [
    "User",
    "RefreshToken",
    "ApiToken",
    "Project",
    "SpecItem",
    "ProjectCredential",
    "ProjectIntegration",
    "Run",
    "RunStageTime",
    "AppMap",
    "RunMetric",
    "LlmUsage",
    "TestCase",
    "TestCaseSpecRef",
    "TestScript",
    "ReviewDecision",
    "TestResult",
    "Artifact",
    "Bug",
    "BugEvidence",
    "BugDuplicate",
    "Verification",
    "VerificationAttempt",
    "SavedTest",
    "SavedTestCoverage",
    "RunSelectedTest",
    "CommitEvent",
    "FailureAnalysis",
    "FailureCandidate",
    "FixSuggestion",
    "AuditLog",
]
