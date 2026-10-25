"""Pydantic schemas for test execution results."""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from kawach.domain.enums import Outcome


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
    failedStep: Optional[int] = None
    totalSteps: Optional[int] = None
    depth: Optional[int] = None
    checkpoint: Optional[str] = None
    videoDuration: Optional[float] = None
    evidenceQuality: Optional[str] = None
    evidenceReason: Optional[str] = None
    failureType: Optional[str] = None


class ResultsSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total: int = 0
    passed: int = 0
    passedWithIssues: int = 0
    failed: int = 0
    assertionFailures: int = 0
    testErrors: int = 0
    scriptErrors: int = 0
    setupErrors: int = 0
    environmentErrors: int = 0
    flaky: int = 0
    inconclusive: int = 0
    notRun: int = 0


class Results(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    startedAt: str
    durationSeconds: float
    workers: int
    tests: List[TestResult] = Field(default_factory=list)
    summary: ResultsSummary = Field(default_factory=ResultsSummary)
