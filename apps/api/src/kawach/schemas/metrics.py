"""Pydantic schemas for run metrics, LLM usage, and benchmarks."""

from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class LlmUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    calls: int = 0
    cacheHits: int = 0
    inputTokens: int = 0
    outputTokens: int = 0
    costUsd: float = 0.0


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
