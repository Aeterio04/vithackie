"""Reviewer agent for autonomous mode catalog review."""

from typing import List

from kawach.core.clock import now_iso
from kawach.schemas import Catalog, ReviewDecision, ReviewLog
from kawach.storage import artifacts as storage


def review_catalog(run_id: str) -> ReviewLog:
    """Review proposed test cases in autonomous mode and return decision log.

    Keeps approve/reject-only powers with logged reasons based on test completeness,
    executable step actions, depth validity, and spec coverage.
    """
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    decisions: List[ReviewDecision] = []

    if catalog and catalog.tests:
        for t in catalog.tests:
            if t.status == "proposed":
                has_title = bool(t.title and t.title.strip())
                has_steps = bool(t.steps and len(t.steps) > 0)
                all_actions_valid = has_steps and all(bool(s.action and s.action.strip()) for s in t.steps)
                is_valid_depth = t.depth > 0

                if has_title and has_steps and all_actions_valid and is_valid_depth:
                    t.status = "approved"
                    spec_note = f"covering {t.specRef}" if t.specRef else "general flow"
                    decisions.append(
                        ReviewDecision(
                            testId=t.id,
                            decision="approve",
                            reason=f"Approved autonomously: {t.category} test (depth {t.depth}, riskScore {t.riskScore}) {spec_note}",
                        )
                    )
                else:
                    t.status = "rejected"
                    reject_reasons = []
                    if not has_title:
                        reject_reasons.append("missing title")
                    if not has_steps:
                        reject_reasons.append("missing steps")
                    if has_steps and not all_actions_valid:
                        reject_reasons.append("empty action string in step")
                    if not is_valid_depth:
                        reject_reasons.append("invalid depth <= 0")
                    decisions.append(
                        ReviewDecision(
                            testId=t.id,
                            decision="reject",
                            reason=f"Rejected autonomously: {', '.join(reject_reasons)}",
                        )
                    )

        catalog.generatedAt = now_iso()
        storage.save_model(run_id, "catalog.json", catalog)

    review_log = ReviewLog(
        runId=run_id,
        reviewedAt=now_iso(),
        decisions=decisions,
    )

    storage.save_model(run_id, "review_log.json", review_log)
    return review_log
