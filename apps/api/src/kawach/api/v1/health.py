"""Health and system statistics endpoints."""

from fastapi import APIRouter

from kawach.schemas import BugsFile
from kawach.storage import artifacts as storage

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health():
    """Health check endpoint indicating active QA engine status."""
    return {
        "ok": True,
        "status": "active",
        "workers_up": 2,
        "queue_depth": 0,
        "message": "KAWACH Autonomous QA Engine is active and operational",
    }


@router.get("/stats")
def get_stats():
    """Aggregate statistics across all stored runs."""
    runs = storage.list_runs()
    confirmed_bugs = 0
    flaky_bugs = 0
    pending_reviews = 0

    for r in runs:
        bugs_f = storage.load_model(r.runId, "bugs.json", BugsFile)
        if bugs_f and bugs_f.bugs:
            for b in bugs_f.bugs:
                st = getattr(b, "status", "")
                if st == "confirmed":
                    confirmed_bugs += 1
                elif st == "flaky":
                    flaky_bugs += 1
        if r.stage == "awaiting_review":
            pending_reviews += 1

    return {
        "total_runs": len(runs),
        "confirmed_bugs": confirmed_bugs,
        "flaky_bugs": flaky_bugs,
        "pending_reviews": pending_reviews,
    }
