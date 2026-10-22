"""Pydantic schemas for test catalogs, test cases, and specs."""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class SpecItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    text: str


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
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    steps: List[Step] = Field(default_factory=list)
    status: Literal["proposed", "approved", "rejected", "edited", "pending"] = "proposed"
    origin: Literal["planner", "human", "fallback", "llm", "heuristic"] = "planner"
    script: Optional[str] = None
    scriptStatus: Literal["pending", "ok", "error"] = "pending"
    scriptError: Optional[str] = None


class Catalog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    generatedAt: str
    tests: List[TestCase] = Field(default_factory=list)
