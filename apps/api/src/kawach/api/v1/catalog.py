"""Catalog and test review endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from kawach.api.deps import get_owned_run
from kawach.api.v1.mappers.catalog_mapper import build_catalog_frontend, transform_test_to_frontend
from kawach.api.v1.mappers.report_mapper import build_review_log_frontend
from kawach.api.v1.mappers.run_mapper import map_stage_to_status
from kawach.db.models.runs import Run as DbRun
from kawach.schemas import ReviewDecision
from kawach.services.catalog_service import add_test_case, batch_review, update_test_case
from kawach.storage import artifacts as storage

router = APIRouter(tags=["catalog"])


class PatchTestPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: Optional[str] = None
    expected_result: Optional[str] = None
    steps: Optional[List[str]] = None
    priority: Optional[str] = None


class AddTestPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt: str


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="ignore")
    test_ids: List[str]
    decision: str  # "approved" | "rejected"
    reason: Optional[str] = ""
    priority_tier: Optional[str] = None  # "P0" | "P0+P1" | "all" | "smoke"


@router.get("/runs/{run_id}/catalog")
def get_catalog(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve catalog test cases formatted for frontend."""
    return build_catalog_frontend(run_id)


@router.patch("/runs/{run_id}/catalog/{test_id}")
def patch_test(
    run_id: str,
    test_id: str,
    payload: PatchTestPayload,
    _run: DbRun = Depends(get_owned_run),
):
    """Update title, priority, or steps of a catalog test."""
    try:
        updated = update_test_case(
            run_id,
            test_id,
            title=payload.title,
            description=payload.expected_result,
            priority=payload.priority,
            steps=[{"action": s} for s in payload.steps] if payload.steps else None,
        )
        return transform_test_to_frontend(updated)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Catalog not found")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Test {test_id} not found")


@router.post("/runs/{run_id}/catalog/test")
def add_custom_test(
    run_id: str,
    payload: AddTestPayload,
    _run: DbRun = Depends(get_owned_run),
):
    """Generate and append a new test case to catalog from prompt. Returns 404 if run not owned."""
    try:
        new_test = add_test_case(run_id, payload.prompt)
        return transform_test_to_frontend(new_test)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/review")
def submit_review(
    run_id: str,
    payload: ReviewSubmission,
    _run: DbRun = Depends(get_owned_run),
):
    """Apply QA decisions to catalog tests and auto-start execution. Returns 404 if run not owned."""
    decisions = [
        ReviewDecision(
            testId=tid,
            decision=payload.decision,  # type: ignore
            reason=payload.reason or "QA Reviewer decision",
        )
        for tid in payload.test_ids
    ]
    try:
        rev_log = batch_review(run_id, decisions)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Catalog not found")

    cat = storage.load_model(run_id, "catalog.json", storage.Catalog)
    remaining_pending = sum(1 for t in cat.tests if getattr(t, "status", "") == "proposed") if cat else 0
    approved_count = sum(1 for t in cat.tests if getattr(t, "status", "") == "approved") if cat else 0

    run = storage.get_run(run_id)

    # Start execution once every test has a decision. Non-blocking, idempotent (a repeated review
    # submission while a run is already executing is ignored by resume_run).
    started = False
    if approved_count > 0:  # approving a subset runs just those tests; resume_run ignores repeats
        from kawach.services.run_service import SpecAlignmentError, resume_run
        try:
            resume_run(run_id, tier=payload.priority_tier)
            started = True
        except SpecAlignmentError as e:
            raise HTTPException(status_code=409, detail=f"Cannot start execution: {e}")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        run = storage.get_run(run_id)

    return {
        "applied_count": len(payload.test_ids),
        "run_status": map_stage_to_status(run.stage),
        "execution_started": started,
    }


@router.get("/runs/{run_id}/review-log")
def get_review_log(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve decision log for catalog reviews. Returns 404 if run not owned."""
    return build_review_log_frontend(run_id)
