"""Reviewer agent for autonomous mode catalog review."""

from typing import List

from kawach.core.clock import now_iso
from kawach.schemas import Catalog, ReviewDecision, ReviewLog
from kawach.storage import artifacts as storage


def review_catalog(run_id: str) -> ReviewLog:
    """Review proposed test cases in autonomous mode and return decision log."""
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    decisions: List[ReviewDecision] = []

    if catalog and catalog.tests:
        for t in catalog.tests:
            if t.status == "proposed":
                if t.title and t.steps:
                    t.status = "approved"
                    spec_note = f"Covers requirements {t.specRef}" if t.specRef else "Valid test flow"
                    decisions.append(
                        ReviewDecision(
                            testId=t.id,
                            decision="approve",
                            reason=f"Approved autonomously: {spec_note}",
                        )
                    )
                else:
                    t.status = "rejected"
                    decisions.append(
                        ReviewDecision(
                            testId=t.id,
                            decision="reject",
                            reason="Rejected autonomously: incomplete test title or steps",
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
