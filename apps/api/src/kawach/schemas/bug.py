"""Pydantic schemas for bugs and bug triage evidence."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from kawach.domain.enums import Category, Severity


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
    depth: Optional[int] = None
    failingPath: List[str] = Field(default_factory=list)
    checkpoint: Optional[str] = None
    reproductionScript: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None


class BugsFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    bugs: List[Bug] = Field(default_factory=list)
