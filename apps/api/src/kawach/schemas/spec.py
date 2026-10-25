"""Structured representation of a QA specification with explicit test cases."""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class SpecRequirement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    text: str


class SpecTestCase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    priority: Literal["P0", "P1", "P2"]
    type: Literal["functional", "informational"] = "functional"
    confidence: Literal["High", "Medium", "Calibrate"] = "Medium"
    specRefs: List[str] = Field(default_factory=list)
    viewport: str = "desktop"
    viewports: List[Dict[str, object]] = Field(default_factory=list)
    preconditions: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    expected: List[str] = Field(default_factory=list)
    calibrationNotes: List[str] = Field(default_factory=list)
    startLine: int = 0


class SpecParseError(BaseModel):
    model_config = ConfigDict(extra="ignore")
    line: int
    tcId: Optional[str] = None
    message: str


class StructuredSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    specHash: str
    globalRules: Dict[str, str] = Field(default_factory=dict)
    requirements: List[SpecRequirement] = Field(default_factory=list)
    testCases: List[SpecTestCase] = Field(default_factory=list)
    knownObservations: List[str] = Field(default_factory=list)
    errors: List[SpecParseError] = Field(default_factory=list)
