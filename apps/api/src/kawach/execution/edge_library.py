"""Data-driven edge-case library for Kawach.

Defines the 14 edge categories prioritized by riskScore:
riskScore = spec criticality x depth x edge severity
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kawach.schemas.catalog import Step, TestCase


@dataclass
class EdgeCaseDefinition:
    tag: str
    category: str
    title_template: str
    description_template: str
    action_template: str
    assertion_template: str
    severity: float  # 1.0 to 3.0
    payload: Optional[str] = None
    tags: List[str] = field(default_factory=list)


EDGE_LIBRARY: Dict[str, EdgeCaseDefinition] = {
    "empty_whitespace": EdgeCaseDefinition(
        tag="empty_whitespace",
        category="input_validation",
        title_template="Reject empty and whitespace-only submission for {target}",
        description_template="Verifies that submitting empty or whitespace-only inputs in {target} triggers validation errors and is rejected.",
        action_template="Fill {target} with whitespace '   \\t\\n' and attempt submission",
        assertion_template="Validation error displayed indicating {target} is required; submission blocked",
        severity=2.0,
        payload="   \t\n",
        tags=["edge", "empty", "whitespace", "validation"],
    ),
    "very_long_input": EdgeCaseDefinition(
        tag="very_long_input",
        category="input_boundary",
        title_template="Handle maximum length and boundary overflow for {target}",
        description_template="Verifies that inputs exceeding standard field boundaries (1000+ characters) in {target} are safely handled without crash.",
        action_template="Fill {target} with 1024 characters of repeated text and submit",
        assertion_template="Gracefully truncated or rejected with boundary length validation message",
        severity=2.5,
        payload="A" * 1024,
        tags=["edge", "boundary", "overflow", "length"],
    ),
    "unicode_emoji_rtl": EdgeCaseDefinition(
        tag="unicode_emoji_rtl",
        category="encoding",
        title_template="Support Unicode, multi-byte emoji, and RTL scripts in {target}",
        description_template="Verifies that Unicode characters, emojis, and right-to-left scripts in {target} are preserved and rendered correctly.",
        action_template="Fill {target} with '🔥 Kawach 🛡️ | مرحبا بالعالم | 日本語テスト' and save",
        assertion_template="Value is saved and rendered without encoding corruption or layout breakage",
        severity=2.0,
        payload="🔥 Kawach 🛡️ | مرحبا بالعالم | 日本語テスト",
        tags=["edge", "unicode", "emoji", "rtl", "i18n"],
    ),
    "html_script_escaping": EdgeCaseDefinition(
        tag="html_script_escaping",
        category="escaping_security",
        title_template="Escape HTML tags and script-like entities in {target}",
        description_template="Verifies that HTML entities and script tags in {target} are rendered as escaped text rather than executable markup.",
        action_template="Fill {target} with '<script>alert(1)</script><b>test</b>' and view display",
        assertion_template="Input is rendered as literal text with tags escaped, no script execution occurs",
        severity=3.0,
        payload="<script>alert(1)</script><b>test</b>",
        tags=["edge", "xss_prevention", "escaping", "security"],
    ),
    "boundary_negative_numbers": EdgeCaseDefinition(
        tag="boundary_negative_numbers",
        category="numerical_boundary",
        title_template="Enforce boundary and sign validation on numeric {target}",
        description_template="Verifies that negative numbers, zero, and out-of-range numeric inputs in {target} are rejected or clamped.",
        action_template="Fill numeric field {target} with '-999999' and boundary values",
        assertion_template="Invalid range error displayed; negative values rejected",
        severity=2.5,
        payload="-999999",
        tags=["edge", "numeric", "boundary", "negative"],
    ),
    "duplicate_submission": EdgeCaseDefinition(
        tag="duplicate_submission",
        category="data_integrity",
        title_template="Prevent duplicate record creation for {target}",
        description_template="Verifies that submitting the same unique entity twice in {target} is blocked with a duplicate conflict error.",
        action_template="Submit entity {target} once successfully, then re-submit identical data",
        assertion_template="System rejects second submission with unique constraint error or 409 conflict message",
        severity=2.5,
        tags=["edge", "duplicates", "uniqueness", "integrity"],
    ),
    "rapid_repeat_submit": EdgeCaseDefinition(
        tag="rapid_repeat_submit",
        category="concurrency_idempotency",
        title_template="Debounce rapid repeat clicks on submit button for {target}",
        description_template="Verifies that rapidly clicking the submit button multiple times in {target} does not create duplicate entries.",
        action_template="Rapidly double-click or multi-click submit button in {target}",
        assertion_template="Button disables on first click; exactly one request processed; duplicate creation prevented",
        severity=3.0,
        tags=["edge", "double_click", "idempotency", "debounce"],
    ),
    "back_forward_refresh": EdgeCaseDefinition(
        tag="back_forward_refresh",
        category="navigation_state",
        title_template="Maintain state integrity across back, forward, and refresh mid-flow in {target}",
        description_template="Verifies that browser back navigation, forward navigation, and refresh during {target} do not corrupt state.",
        action_template="Enter data in {target}, navigate back, navigate forward, and refresh page",
        assertion_template="Page recovers gracefully without unhandled exception or data corruption",
        severity=2.0,
        tags=["edge", "browser_history", "refresh", "navigation"],
    ),
    "interrupted_flow": EdgeCaseDefinition(
        tag="interrupted_flow",
        category="interaction_interruption",
        title_template="Handle interrupted workflow (close modal, switch tab, re-enter) in {target}",
        description_template="Verifies that closing a modal or switching away during {target} and re-opening recovers cleanly.",
        action_template="Open {target} modal, input partial data, close with Escape or cancel, re-open modal",
        assertion_template="Modal state is either safely reset or preserved cleanly; no stuck overlays or backdrop locks",
        severity=2.0,
        tags=["edge", "modal", "interruption", "workflow"],
    ),
    "expired_session": EdgeCaseDefinition(
        tag="expired_session",
        category="auth_session",
        title_template="Handle expired or invalidated session mid-flow in {target}",
        description_template="Verifies that if an authentication session expires while user is on {target}, submission redirects to login without crash.",
        action_template="Prepare submission in {target}, clear auth cookies/tokens, then submit form",
        assertion_template="User redirected to login page with friendly session expired notice; unsaved data prompt if supported",
        severity=2.5,
        tags=["edge", "session", "auth", "expiry"],
    ),
    "order_permutations": EdgeCaseDefinition(
        tag="order_permutations",
        category="flow_order",
        title_template="Validate out-of-order interaction sequences in {target}",
        description_template="Verifies that completing steps in reverse or out-of-order sequence in {target} correctly guides user.",
        action_template="Attempt step 2 before completing required step 1 in {target}",
        assertion_template="Appropriate step validation prompts appear; prerequisite steps enforced",
        severity=1.5,
        tags=["edge", "order_of_operations", "flow_logic"],
    ),
    "keyboard_only": EdgeCaseDefinition(
        tag="keyboard_only",
        category="accessibility",
        title_template="Complete {target} using keyboard navigation exclusively",
        description_template="Verifies full accessibility for {target} using Tab, Shift+Tab, Enter, and Space keys without pointer interaction.",
        action_template="Navigate through all interactive controls in {target} using Tab key and activate with Enter",
        assertion_template="All controls receive visible focus outline; forms submittable via keyboard",
        severity=1.5,
        tags=["edge", "keyboard", "accessibility", "a11y"],
    ),
    "viewport_changes": EdgeCaseDefinition(
        tag="viewport_changes",
        category="responsive",
        title_template="Verify layout and control visibility on viewport resize for {target}",
        description_template="Verifies that resizing between mobile (375x667) and desktop (1280x800) keeps controls visible in {target}.",
        action_template="Change viewport to mobile 375x667 during {target} and inspect interactive elements",
        assertion_template="No horizontal overflow or overlapping buttons; all controls remain accessible",
        severity=1.5,
        tags=["edge", "viewport", "mobile", "responsive"],
    ),
    "network_failure": EdgeCaseDefinition(
        tag="network_failure",
        category="network_resilience",
        title_template="Display user-friendly error message on network failure during {target}",
        description_template="Verifies that simulated network interruption or server 500 error during {target} shows readable feedback.",
        action_template="Trigger submission in {target} while simulating network failure or 500 server error",
        assertion_template="User-friendly retry banner displayed; no unhandled promise rejection or blank screen",
        severity=2.5,
        tags=["edge", "network", "resilience", "error_handling"],
    ),
}


def compute_risk_score(priority: str, depth: int, severity: float = 1.0) -> float:
    """Calculate riskScore = spec criticality x depth x edge severity."""
    crit_map = {
        "critical": 3.0,
        "high": 2.5,
        "medium": 2.0,
        "low": 1.0,
    }
    spec_crit = crit_map.get(priority.lower(), 2.0)
    clamped_depth = max(1, min(depth, 5))
    clamped_sev = max(1.0, min(severity, 3.0))
    return round(spec_crit * clamped_depth * clamped_sev, 2)
