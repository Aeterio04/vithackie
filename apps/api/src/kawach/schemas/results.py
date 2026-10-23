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
