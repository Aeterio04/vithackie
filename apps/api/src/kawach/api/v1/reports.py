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


@router.get("/runs/{run_id}/report.pdf")
def get_report_pdf(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Download compiled QA verification report as an A4 PDF document."""
    from fastapi.responses import FileResponse
    from kawach.execution.report_generator import generate_all_reports

    run_dir = storage.run_dir(run_id)
    pdf_path = run_dir / "report.pdf"
    if not pdf_path.exists():
        res = generate_all_reports(run_id)
        if res.get("status") != "ready" or not pdf_path.exists():
            raise HTTPException(status_code=500, detail="Failed to compile report PDF")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"report-{run_id}.pdf",
    )


@router.get("/runs/{run_id}/report.md")
def get_report_markdown(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Download compiled QA verification report as a GitHub-flavored Markdown document."""
    from fastapi.responses import FileResponse
    from kawach.execution.report_generator import generate_all_reports

    run_dir = storage.run_dir(run_id)
    md_path = run_dir / "report.md"
    if not md_path.exists():
        res = generate_all_reports(run_id)
        if res.get("status") != "ready" or not md_path.exists():
            raise HTTPException(status_code=500, detail="Failed to compile report Markdown")

    return FileResponse(
        path=str(md_path),
        media_type="text/markdown",
        filename=f"report-{run_id}.md",
    )


@router.post("/runs/{run_id}/report/regenerate")
def regenerate_report(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Rebuild all report formats (Markdown, HTML, PDF) from stored run artifacts."""
    from kawach.execution.report_generator import generate_all_reports

    res = generate_all_reports(run_id, force_regenerate=True)
    return {
        "run_id": run_id,
        "report_status": res.get("status", "ready"),
        "has_pdf": (storage.run_dir(run_id) / "report.pdf").exists(),
        "has_md": (storage.run_dir(run_id) / "report.md").exists(),
        "error": res.get("error"),
    }
