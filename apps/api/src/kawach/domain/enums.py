"""Domain enumerations and string union types matching CONTRACTS.md Section 5."""

from typing import List, Literal

# String Unions
Stage = Literal[
    "created",
    "exploring",
    "planning",
    "awaiting_review",
    "scripting",
    "running",
    "verifying",
    "reporting",
    "done",
    "done_with_environment_issue",
    "script_generation_failed",
    "failed",
    "cancelled",
]

Mode = Literal["manual", "autonomous"]

Outcome = Literal[
    "passed",
    "passed_with_issues",
    "failed",
    "assertion_failure",
    "test_error",
    "script_error",
    "setup_error",
    "environment_error",
    "flaky",
    "inconclusive",
    "not_run",
]

Category = Literal[
    "validation",
    "auth",
    "data",
    "navigation",
    "console",
    "network",
    "ui",
    "other",
]

Severity = Literal["critical", "high", "medium", "low"]

BugStatus = Literal["suspected", "confirmed", "flaky", "not_reproduced"]

TriggerType = Literal["manual", "commit", "cron", "webhook"]

TestStatus = Literal["proposed", "approved", "rejected", "edited", "pending"]

STAGES_ORDER: List[Stage] = [
    "created",
    "exploring",
    "planning",
    "awaiting_review",
    "scripting",
    "running",
    "verifying",
    "reporting",
    "done",
    "done_with_environment_issue",
    "failed",
    "cancelled",
]
