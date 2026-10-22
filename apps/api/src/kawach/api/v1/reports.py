"""Reporting and metrics aggregation endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from kawach.api.deps import get_owned_run
from kawach.api.v1.mappers.report_mapper import build_report_frontend
from kawach.db.models.runs import Run as DbRun
from kawach.schemas import Metrics, Results
from kawach.services.report_service import build_metrics, build_report
from kawach.storage import artifacts as storage

router = APIRouter(tags=["reports"])


@router.get("/runs/{run_id}/report")
def get_report(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve complete QA report including verification funnel and coverage."""
    try:
        return build_report_frontend(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")


@router.get("/runs/{run_id}/results")
def get_results(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve raw test results."""
    results = storage.load_model(run_id, "results.json", Results)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")
    return results


@router.get("/runs/{run_id}/metrics")
def get_metrics(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve calculated run metrics."""
    metrics = storage.load_model(run_id, "metrics.json", Metrics)
    if not metrics:
        metrics = build_metrics(run_id)
    return metrics
