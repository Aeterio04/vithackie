"""Pydantic v2 models representing the shared contracts.

All field names are exact camelCase matching CONTRACTS.md Section 5.
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

# String Unions
Stage = Literal[
    "created",
    "exploring",
    "planning",
    "awaiting_review",
    "scripting",
    "running",
    "verifying",
    "reporting",
    "done",
    "failed",
]

Mode = Literal["manual", "autonomous"]

Outcome = Literal["passed", "assertion_failure", "test_error"]

Category = Literal[
    "validation",
    "auth",
    "data",
    "navigation",
    "console",
    "network",
    "ui",
    "other",
]

Severity = Literal["critical", "high", "medium", "low"]


# Base schemas
class SpecItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    text: str


class Budgets(BaseModel):
    model_config = ConfigDict(extra="ignore")
    maxPages: int = 10
    exploreSeconds: int = 90
    maxTests: int = 12
    testTimeoutMs: int = 30000


class RunInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    createdAt: str
    targetUrl: str
    prompt: str = ""
    specRaw: str
    spec: List[SpecItem] = Field(default_factory=list)
    username: str = ""
    mode: Mode = "manual"
    budgets: Budgets = Field(default_factory=Budgets)


class Progress(BaseModel):
    model_config = ConfigDict(extra="ignore")
    step: str
    done: int
    total: int


class StageTime(BaseModel):
    model_config = ConfigDict(extra="ignore")
    startedAt: str
    endedAt: Optional[str] = None


class Run(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    createdAt: str
    updatedAt: str
    stage: Stage = "created"
    mode: Mode = "manual"
    targetUrl: str
    error: Optional[str] = None
    progress: Optional[Progress] = None
    stageTimes: Dict[str, StageTime] = Field(default_factory=dict)
    golden: bool = False


class LlmUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    calls: int = 0
    cacheHits: int = 0
    inputTokens: int = 0
    outputTokens: int = 0
    costUsd: float = 0.0


# Explorer Models
class FieldInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    label: str
    type: str
    name: str
    required: bool = False


class FormInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    action: str = ""
    method: str = "GET"
    submitText: Optional[str] = None
    fields: List[FieldInfo] = Field(default_factory=list)


class HeadingInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    level: int
    text: str


class LinkInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    href: str


class ButtonInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str


class PageInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str
    path: str
    title: str
    status: int
    requiresAuth: bool = False
    headings: List[HeadingInfo] = Field(default_factory=list)
    links: List[LinkInfo] = Field(default_factory=list)
    buttons: List[ButtonInfo] = Field(default_factory=list)
    forms: List[FormInfo] = Field(default_factory=list)
    consoleErrors: List[str] = Field(default_factory=list)


class Feature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    description: str
    pages: List[str] = Field(default_factory=list)


class LoginInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    attempted: bool = False
    success: bool = False
    url: Optional[str] = None
    note: Optional[str] = None


class AppMapStats(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pagesVisited: int = 0
    durationSeconds: float = 0.0
    budgetHit: Optional[Literal["pages", "time"]] = None


class AppMap(BaseModel):
    model_config = ConfigDict(extra="ignore")
    baseUrl: str
    generatedAt: str
    login: LoginInfo = Field(default_factory=LoginInfo)
    pages: List[PageInfo] = Field(default_factory=list)
    summary: str = ""
    features: List[Feature] = Field(default_factory=list)
    stats: AppMapStats = Field(default_factory=AppMapStats)
    error: Optional[str] = None


# Planner / Reviewer Models
class Step(BaseModel):
    model_config = ConfigDict(extra="ignore")
    n: int
    action: str
    expected: Optional[str] = None


class TestCase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    description: str
    specRef: List[str] = Field(default_factory=list)
    priority: Literal["high", "medium", "low"] = "medium"
    steps: List[Step] = Field(default_factory=list)
    status: Literal["proposed", "approved", "rejected"] = "proposed"
    origin: Literal["planner", "human", "fallback"] = "planner"
    script: Optional[str] = None
    scriptStatus: Literal["pending", "ok", "error"] = "pending"
    scriptError: Optional[str] = None


class Catalog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    generatedAt: str
    tests: List[TestCase] = Field(default_factory=list)


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    testId: str
    decision: Literal["approve", "reject"]
    reason: str


class ReviewLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    reviewedAt: str
    decisions: List[ReviewDecision] = Field(default_factory=list)


# Runner / Triage Models
class TestResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    testId: str
    title: str
    file: str
    source: Literal["planned", "exploratory"]
    outcome: Outcome
    durationMs: int
    errorMessage: Optional[str] = None
    evidenceDir: Optional[str] = None


class ResultsSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total: int = 0
    passed: int = 0
    assertionFailures: int = 0
    testErrors: int = 0


class Results(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    startedAt: str
    durationSeconds: float
    workers: int
    tests: List[TestResult] = Field(default_factory=list)
    summary: ResultsSummary = Field(default_factory=ResultsSummary)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    screenshot: Optional[str] = None
    video: Optional[str] = None
    trace: Optional[str] = None
    console: Optional[str] = None
    network: Optional[str] = None


class BugReplay(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reproduced: int
    attempts: int


class Bug(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    testId: str
    source: Literal["planned", "exploratory"]
    title: str
    grep: str
    file: str
    category: Category
    severity: Severity
    specRef: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    expected: str
    actual: str
    errorMessage: str
    signature: str
    duplicates: List[str] = Field(default_factory=list)
    evidence: Evidence = Field(default_factory=Evidence)
    status: Literal["candidate", "confirmed", "flaky", "not_reproduced"]
    replay: Optional[BugReplay] = None


class BugsFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    bugs: List[Bug] = Field(default_factory=list)


class VerificationAttempt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    attempt: int
    reproduced: bool
    outcome: Outcome
    errorMessage: Optional[str] = None
    durationMs: int


class Verification(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bugId: str
    verifiedAt: str
    attempts: List[VerificationAttempt] = Field(default_factory=list)
    reproduced: int
    status: Literal["confirmed", "flaky", "not_reproduced"]


class BlockedRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ts: str
    testId: str
    url: str
    method: str
    resourceType: str


class ParallelTiming(BaseModel):
    model_config = ConfigDict(extra="ignore")
    workers1Seconds: float
    workers4Seconds: float
    speedup: float


# Metrics / Benchmark Models
class MetricsTests(BaseModel):
    model_config = ConfigDict(extra="ignore")
    planned: int = 0
    approved: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0


class MetricsBugs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    candidates: int = 0
    confirmed: int = 0
    flaky: int = 0
    notReproduced: int = 0


class MetricsCoverage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pagesInMap: int = 0
    pagesExercised: int = 0
    formsInMap: int = 0
    formsExercised: int = 0
    specItems: int = 0
    specItemsCovered: int = 0


class MetricsSafety(BaseModel):
    model_config = ConfigDict(extra="ignore")
    blockedRequests: int = 0


class Metrics(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    wallClockSeconds: float
    stageSeconds: Dict[str, float] = Field(default_factory=dict)
    tests: MetricsTests = Field(default_factory=MetricsTests)
    bugs: MetricsBugs = Field(default_factory=MetricsBugs)
    coverage: MetricsCoverage = Field(default_factory=MetricsCoverage)
    llm: LlmUsage = Field(default_factory=LlmUsage)
    parallel: Optional[ParallelTiming] = None
    safety: MetricsSafety = Field(default_factory=MetricsSafety)


class BenchmarkMatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bugId: str
    groundTruthId: Optional[str] = None


class Benchmark(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    groundTruthTotal: int
    matches: List[BenchmarkMatch] = Field(default_factory=list)
    truePositives: int
    falsePositives: int
    recall: float
    precision: float
    replayRate: float


# API Views
class RunView(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run: Run
    input: RunInput
    appMap: Optional[AppMap] = None
    catalog: Optional[Catalog] = None
    reviewLog: Optional[ReviewLog] = None
    results: Optional[Results] = None
    bugs: List[Bug] = Field(default_factory=list)
    verifications: List[Verification] = Field(default_factory=list)
    metrics: Optional[Metrics] = None
    hasReport: bool = False


class RunListItemCounts(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tests: int = 0
    bugs: int = 0
    confirmed: int = 0
    flaky: int = 0


class RunListItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    createdAt: str
    stage: Stage
    mode: Mode
    targetUrl: str
    counts: RunListItemCounts = Field(default_factory=RunListItemCounts)
