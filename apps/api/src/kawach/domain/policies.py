# SCAFFOLD: not implemented
"""Domain policy rules and invariants governing automated fix safety.

Defines the objective boundary for "small fix" eligibility vs escalation
per Section 8 / Appendix A specifications.
"""

from typing import List, Literal, Optional

RiskClass = Literal["small", "large"]

PROTECTED_BRANCHES: tuple = ("main", "master", "prod", "production", "release")

DEFAULT_MAX_FILES: int = 1
DEFAULT_MAX_LINES: int = 20
DEFAULT_FORBIDDEN_PATHS: List[str] = [
    "auth",
    "login",
    "password",
    "payment",
    "billing",
    "migrations",
    "alembic",
    "schema",
    "security",
    ".env",
]



def is_forbidden_path(path: str, forbidden_patterns: Optional[List[str]] = None) -> bool:
    """Check if a file path touches sensitive or restricted submodules."""
    patterns = forbidden_patterns if forbidden_patterns is not None else DEFAULT_FORBIDDEN_PATHS
    normalized = path.lower().replace("\\", "/")
    for pattern in patterns:
        p = pattern.lower().strip()
        if not p:
            continue
        # Substring or path segment match
        if p in normalized.split("/") or p in normalized:
            return True
    return False


def is_small_fix(
    files_changed: List[str],
    lines_changed: int,
    forbidden_paths: Optional[List[str]] = None,
    max_files: int = DEFAULT_MAX_FILES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> bool:
    """Evaluate whether an automated fix satisfies the objective 'small fix' policy.

    A fix qualifies as 'small' only if:
    1. The number of changed files <= max_files (default: 1).
    2. The number of lines changed <= max_lines (default: 20).
    3. None of the changed files reside within forbidden paths (auth, payment, migrations).
    """
    if len(files_changed) == 0:
        return False

    if len(files_changed) > max_files:
        return False

    if lines_changed > max_lines:
        return False

    for file_path in files_changed:
        if is_forbidden_path(file_path, forbidden_paths):
            return False

    return True


def classify_fix_risk(
    files_changed: List[str],
    lines_changed: int,
    forbidden_paths: Optional[List[str]] = None,
    max_files: int = DEFAULT_MAX_FILES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> RiskClass:
    """Return 'small' if safe for automated PR creation; otherwise 'large' for escalation."""
    return (
        "small"
        if is_small_fix(
            files_changed=files_changed,
            lines_changed=lines_changed,
            forbidden_paths=forbidden_paths,
            max_files=max_files,
            max_lines=max_lines,
        )
        else "large"
    )


def is_fix_allowed(
    files_changed: List[str],
    lines_changed: int = 0,
    target_branch: str = "main",
    forbidden_paths: Optional[List[str]] = None,
    max_files: int = DEFAULT_MAX_FILES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> bool:
    """Evaluate whether an automated fix is permitted to be applied.

    Fails if attempting direct push to protected branch or exceeding small fix bounds.
    """
    if target_branch in PROTECTED_BRANCHES:
        return False
    return is_small_fix(
        files_changed=files_changed,
        lines_changed=lines_changed,
        forbidden_paths=forbidden_paths,
        max_files=max_files,
        max_lines=max_lines,
    )

