"""Pydantic schemas for test catalogs, test cases, and specs."""

from typing import Any, Dict, List, Literal, Optional
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
    checkpoint: Optional[str] = None
    assertion: Optional[str] = None
    locator: Optional[str] = None


class TestCase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    description: str
    specRef: List[str] = Field(default_factory=list)
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    depth: int = 1
    category: Literal["single_step", "journey", "deep_path", "edge_case"] = "single_step"
    preconditions: List[str] = Field(default_factory=list)
    setup: List[str] = Field(default_factory=list)
    edgeTags: List[str] = Field(default_factory=list)
    coverageRef: List[str] = Field(default_factory=list)
    riskScore: float = 0.0
    steps: List[Step] = Field(default_factory=list)
    status: Literal["proposed", "approved", "rejected", "edited", "pending"] = "proposed"
    origin: Literal["planner", "human", "fallback", "llm", "heuristic"] = "planner"
    script: Optional[str] = None
    scriptStatus: Literal["pending", "ok", "error"] = "pending"
    scriptError: Optional[str] = None


class CoverageMatrix(BaseModel):
    model_config = ConfigDict(extra="ignore")
    specItems: List[str] = Field(default_factory=list)
    depthLevels: Dict[str, int] = Field(default_factory=dict)
    edgeCategories: Dict[str, int] = Field(default_factory=dict)
    matrix: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)


class Catalog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    generatedAt: str
    tests: List[TestCase] = Field(default_factory=list)
    coverageMatrix: Optional[CoverageMatrix] = None
