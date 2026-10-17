"""Planner agent that designs a catalog of test cases.

Implemented by Track B.
"""

from app.models import Catalog, TestCase


def plan_catalog(run_id: str) -> Catalog:
    """Generate a catalog of test cases from app map and spec.

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements plan_catalog")


def plan_single_test(run_id: str, user_prompt: str) -> TestCase:
    """Plan a single test case from a user-provided prompt string.

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements plan_single_test")
