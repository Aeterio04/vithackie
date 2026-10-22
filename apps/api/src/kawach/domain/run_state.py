"""Run state transition rules and state machine guards."""

from typing import Dict, Set
from kawach.core.errors import StageTransitionError

ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "created": {"exploring", "failed", "cancelled"},
    "exploring": {"planning", "failed", "cancelled"},
    "planning": {"awaiting_review", "scripting", "failed", "cancelled"},
    "awaiting_review": {"scripting", "failed", "cancelled"},
    "scripting": {"running", "failed", "cancelled"},
    "running": {"verifying", "failed", "cancelled"},
    "verifying": {"reporting", "failed", "cancelled"},
    "reporting": {"done", "failed", "cancelled"},
    "done": set(),
    "failed": set(),
    "cancelled": set(),
}


def can_transition(current: str, target: str) -> bool:
    """Check whether a stage transition is permissible."""
    if current == target:
        return True
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    return target in allowed


def validate_transition(current: str, target: str) -> None:
    """Validate that transition is allowed; raise StageTransitionError if not."""
    if not can_transition(current, target):
        raise StageTransitionError(current, target)
