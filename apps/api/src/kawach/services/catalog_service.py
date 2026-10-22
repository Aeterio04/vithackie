"""Catalog management service for viewing, editing, and reviewing test cases."""

from typing import Any, Dict, List, Optional

from kawach.agents.planner import plan_single_test
from kawach.core.clock import now_iso
from kawach.schemas import Catalog, ReviewDecision, ReviewLog, Step, TestCase
from kawach.services.run_service import log_pipeline
from kawach.storage import artifacts as storage


def get_catalog(run_id: str) -> Optional[Catalog]:
    """Retrieve catalog.json for a run."""
    return storage.load_model(run_id, "catalog.json", Catalog)


def update_test_case(
    run_id: str,
    test_id: str,
    *,
    status: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
) -> TestCase:
    """Update properties or review status of a test case in catalog.json."""
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    if not catalog:
        raise FileNotFoundError(f"Catalog for run {run_id} not found")

    target_test: Optional[TestCase] = None
    for t in catalog.tests:
        if t.id == test_id:
            target_test = t
            break

    if not target_test:
        raise KeyError(f"Test {test_id} not found in catalog of run {run_id}")

    if status is not None:
        valid_status = status.lower()
        if valid_status not in ("proposed", "approved", "rejected", "edited", "pending"):
            raise ValueError(f"Invalid status: {status}")
        target_test.status = valid_status  # type: ignore

    if title is not None:
        target_test.title = title
    if description is not None:
        target_test.description = description
    if priority is not None:
        target_test.priority = priority.lower()  # type: ignore

    if steps is not None:
        new_steps = []
        for idx, s in enumerate(steps):
            if isinstance(s, dict):
                new_steps.append(Step(n=idx + 1, action=s.get("action", ""), expected=s.get("expected")))
            elif isinstance(s, str):
                new_steps.append(Step(n=idx + 1, action=s, expected=None))
        target_test.steps = new_steps

    catalog.generatedAt = now_iso()
    storage.save_model(run_id, "catalog.json", catalog)

    log_pipeline(
        run_id,
        f"Test case {test_id} updated (status: {target_test.status}).",
        source="catalog",
    )
    return target_test


def add_test_case(run_id: str, prompt: str) -> TestCase:
    """Generate and append a single new test case from a user prompt."""
    test = plan_single_test(run_id, prompt)
    log_pipeline(
        run_id,
        f"Created customized test scenario {test.id}: '{test.title}'",
        source="planner",
    )
    return test


def batch_review(run_id: str, decisions: List[ReviewDecision]) -> ReviewLog:
    """Apply a batch of review decisions to catalog.json and record review_log.json."""
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    if not catalog:
        raise FileNotFoundError(f"Catalog for run {run_id} not found")

    decision_map = {d.testId: d for d in decisions}
    recorded_decisions: List[ReviewDecision] = []

    for t in catalog.tests:
        if t.id in decision_map:
            dec = decision_map[t.id]
            clean_dec = dec.decision.lower()
            if clean_dec in ("approve", "approved"):
                t.status = "approved"
            elif clean_dec in ("reject", "rejected"):
                t.status = "rejected"
            recorded_decisions.append(
                ReviewDecision(
                    testId=t.id,
                    decision=t.status,  # type: ignore
                    reason=dec.reason or f"User decision: {t.status}",
                )
            )

    catalog.generatedAt = now_iso()
    storage.save_model(run_id, "catalog.json", catalog)

    review_log = ReviewLog(
        runId=run_id,
        reviewedAt=now_iso(),
        decisions=recorded_decisions,
    )
    storage.save_model(run_id, "review_log.json", review_log)

    log_pipeline(
        run_id,
        f"Batch review applied: {len(recorded_decisions)} tests updated.",
        source="catalog",
    )
    return review_log
