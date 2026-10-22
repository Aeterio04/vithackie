# SCAFFOLD: not implemented
"""Fix suggestion and automated PR creation service interface and stub.

Per Section 8 / Appendix A specifications:
- Proposes patches for localized defects.
- Classifies risk ("small" vs "large").
- Validates fixes using 3x verification replays.
- Generates Pull Requests for low-risk changes (never direct pushes).
"""

from typing import Protocol, runtime_checkable

from kawach.schemas.commit_loop import FixSuggestionRead


@runtime_checkable
class FixServiceProtocol(Protocol):
    """Protocol defining the fix proposal and remediation interface."""

    def suggest_fix(self, analysis_id: str) -> FixSuggestionRead:
        """Synthesize a code patch diff for a localized regression defect."""
        ...

    def validate_fix(self, fix_id: str) -> bool:
        """Execute 3x replay verification to prove defect remediation without side effects."""
        ...

    def create_auto_fix_pr(self, fix_id: str) -> str:
        """Open a GitHub pull request with the validated fix and test proof attached."""
        ...


class FixService:
    """Scaffolded fix service implementation raising NotImplementedError."""

    def suggest_fix(self, analysis_id: str) -> FixSuggestionRead:
        raise NotImplementedError("Fix synthesis is scaffolded for future product releases.")

    def validate_fix(self, fix_id: str) -> bool:
        raise NotImplementedError("Fix validation is scaffolded for future product releases.")

    def create_auto_fix_pr(self, fix_id: str) -> str:
        raise NotImplementedError("Auto-fix PR creation is scaffolded for future product releases.")
