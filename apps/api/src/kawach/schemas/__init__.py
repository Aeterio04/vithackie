"""Pydantic v2 schemas representing the shared contracts.

All field names are exact camelCase matching CONTRACTS.md Section 5.
"""

from kawach.domain.enums import (
    Category,
    Mode,
    Outcome,
    Severity,
    Stage,
)
from kawach.schemas.app_map import (
    AppMap,
    AppMapStats,
    ButtonInfo,
    Feature,
    FieldInfo,
    FormInfo,
    HeadingInfo,
    LinkInfo,
    LoginInfo,
    PageInfo,
)
from kawach.schemas.bug import Bug, BugReplay, BugsFile, Evidence
from kawach.schemas.catalog import Catalog, SpecItem, Step, TestCase
from kawach.schemas.metrics import (
    Benchmark,
    BenchmarkMatch,
    BlockedRequest,
    LlmUsage,
    Metrics,
    MetricsBugs,
    MetricsCoverage,
    MetricsSafety,
    MetricsTests,
    ParallelTiming,
)
from kawach.schemas.report import ReviewDecision, ReviewLog
from kawach.schemas.results import Results, ResultsSummary, TestResult
from kawach.schemas.run import (
    Budgets,
    Progress,
    Run,
    RunInput,
    RunListItem,
    RunListItemCounts,
    RunView,
    StageTime,
)
from kawach.schemas.verification import Verification, VerificationAttempt

__all__ = [
    # Enums / Unions
    "Stage",
    "Mode",
    "Outcome",
    "Category",
    "Severity",
    # AppMap
    "FieldInfo",
    "FormInfo",
    "HeadingInfo",
    "LinkInfo",
    "ButtonInfo",
    "PageInfo",
    "Feature",
    "LoginInfo",
    "AppMapStats",
    "AppMap",
    # Catalog / Spec
    "SpecItem",
    "Step",
    "TestCase",
    "Catalog",
    # Bug
    "Evidence",
    "BugReplay",
    "Bug",
    "BugsFile",
    # Run
    "Budgets",
    "RunInput",
    "Progress",
    "StageTime",
    "Run",
    "RunListItemCounts",
    "RunListItem",
    "RunView",
    # Results
    "TestResult",
    "ResultsSummary",
    "Results",
    # Report / Review
    "ReviewDecision",
    "ReviewLog",
    # Verification
    "VerificationAttempt",
    "Verification",
    # Metrics
    "LlmUsage",
    "BlockedRequest",
    "ParallelTiming",
    "MetricsTests",
    "MetricsBugs",
    "MetricsCoverage",
    "MetricsSafety",
    "Metrics",
    "BenchmarkMatch",
    "Benchmark",
]
