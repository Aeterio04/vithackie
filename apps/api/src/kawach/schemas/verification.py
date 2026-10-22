"""Pydantic schemas for bug reproduction verifications."""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from kawach.domain.enums import Outcome


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
