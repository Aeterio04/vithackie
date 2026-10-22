# SCAFFOLD: not implemented
"""Regression testing orchestration service interface and stub.

Per Section 8 / Appendix A specifications:
- Selects saved tests based on diff-aware coverage mapping.
- Triggers regression suites upon commit webhook events.
"""

from typing import List, Optional, Protocol, runtime_checkable

from kawach.schemas.saved_tests import SavedTestRead


@runtime_checkable
class RegressionServiceProtocol(Protocol):
    """Protocol defining the regression testing service interface."""

    def select_tests_for_diff(self, project_id: str, files_changed: List[str]) -> List[str]:
        """Identify saved tests whose coverage intersects with modified files."""
        ...

    def save_test(self, project_id: str, run_id: str, test_id: str, name: Optional[str] = None) -> SavedTestRead:
        """Promote an executed test case to the project's permanent regression suite."""
        ...

    def run_regression_suite(self, project_id: str, test_ids: List[str], commit_sha: Optional[str] = None) -> str:
        """Trigger an execution run for the selected saved tests."""
        ...


class RegressionService:
    """Scaffolded regression service implementation raising NotImplementedError."""

    def select_tests_for_diff(self, project_id: str, files_changed: List[str]) -> List[str]:
        raise NotImplementedError("Diff-aware test selection is scaffolded for future product releases.")

    def save_test(self, project_id: str, run_id: str, test_id: str, name: Optional[str] = None) -> SavedTestRead:
        raise NotImplementedError("Saving tests to regression library is scaffolded for future product releases.")

    def run_regression_suite(self, project_id: str, test_ids: List[str], commit_sha: Optional[str] = None) -> str:
        raise NotImplementedError("Running regression suites is scaffolded for future product releases.")
