"""Domain layer for KAWACH."""

from kawach.domain.enums import (
    Stage,
    STAGES_ORDER,
    Mode,
    Outcome,
    Category,
    Severity,
    BugStatus,
    TriggerType,
    TestStatus,
)
from kawach.domain.run_state import can_transition, validate_transition, ALLOWED_TRANSITIONS
from kawach.domain.policies import is_fix_allowed, PROTECTED_BRANCHES

__all__ = [
    "Stage",
    "STAGES_ORDER",
    "Mode",
    "Outcome",
    "Category",
    "Severity",
    "BugStatus",
    "TriggerType",
    "TestStatus",
    "can_transition",
    "validate_transition",
    "ALLOWED_TRANSITIONS",
    "is_fix_allowed",
    "PROTECTED_BRANCHES",
]
