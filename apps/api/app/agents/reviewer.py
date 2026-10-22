"""Reviewer agent for autonomous mode catalog review.

Implemented by Track B.
"""

from datetime import datetime, timezone
from typing import List

from app.models import Catalog, ReviewDecision, ReviewLog
from app import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def review_catalog(run_id: str) -> ReviewLog:
    """Review proposed test cases in autonomous mode and return decision log."""
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    decisions: List[ReviewDecision] = []

    if catalog and catalog.tests:
        for t in catalog.tests:
            if t.status == "proposed":
                # Autonomous approval: verify test has title and steps
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

        catalog.generatedAt = _now_iso()
        storage.save_model(run_id, "catalog.json", catalog)

    review_log = ReviewLog(
        runId=run_id,
        reviewedAt=_now_iso(),
        decisions=decisions,
    )

    storage.save_model(run_id, "review_log.json", review_log)
    return review_log
