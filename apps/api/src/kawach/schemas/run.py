"""Pydantic schemas for runs, run inputs, progress, and run views."""

from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from kawach.domain.enums import Mode, Stage
from kawach.schemas.catalog import Catalog, SpecItem
from kawach.schemas.app_map import AppMap
from kawach.schemas.bug import Bug
from kawach.schemas.report import ReviewLog
from kawach.schemas.results import Results
from kawach.schemas.verification import Verification
from kawach.schemas.metrics import Metrics


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
    specRaw: str = ""
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
    projectId: Optional[str] = None


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
