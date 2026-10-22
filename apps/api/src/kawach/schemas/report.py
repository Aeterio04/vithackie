"""Pydantic schemas for review decisions and review logs."""

from typing import List, Literal
from pydantic import BaseModel, ConfigDict, Field


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    testId: str
    decision: Literal["approve", "approved", "reject", "rejected"]
    reason: str


class ReviewLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runId: str
    reviewedAt: str
    decisions: List[ReviewDecision] = Field(default_factory=list)
