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
    ActionEdge,
    AppMap,
    AppMapStats,
    ButtonInfo,
    Feature,
    FieldInfo,
    FormInfo,
    FrontierState,
    HeadingInfo,
    Journey,
    LinkInfo,
    LoginInfo,
    PageInfo,
    StateNode,
)
from kawach.schemas.tokens import (
    ApiClient,
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenRead,
)
from kawach.schemas.bug import Bug, BugReplay, BugsFile, Evidence
from kawach.schemas.catalog import Catalog, CoverageMatrix, SpecItem, Step, TestCase
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
    "StateNode",
    "ActionEdge",
    "Journey",
    "FrontierState",
    "AppMap",
    # Tokens
    "ApiClient",
    "ApiTokenCreate",
    "ApiTokenRead",
    "ApiTokenCreated",
    # Catalog / Spec
    "SpecItem",
    "Step",
    "TestCase",
    "CoverageMatrix",
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
