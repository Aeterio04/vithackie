# SCAFFOLD: not implemented
"""GitHub integration safety policy constants.

Enforces invariants specified in Section 8 / Appendix A:
- Auto-fix may ONLY open a pull request.
- Auto-fix must NEVER push directly to default branches (main, master).
"""

# Hard architectural invariants
ALLOW_DIRECT_PUSH: bool = False
AUTO_FIX_TARGET: str = "pull_request"
FORBIDDEN_BRANCHES: tuple = ("main", "master", "prod", "production", "release")


def can_push_directly(target_branch: str) -> bool:
    """Evaluate if direct push is permitted. Always returns False by safety contract."""
    return False


def get_auto_fix_target() -> str:
    """Return the designated automated remediation mechanism ('pull_request')."""
    return AUTO_FIX_TARGET
