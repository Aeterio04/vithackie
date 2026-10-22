"""ZIP export endpoints for runs and standalone Playwright suites."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from kawach.api.deps import get_current_user, get_owned_run
from kawach.db.models.identity import User
from kawach.db.models.runs import Run as DbRun
from kawach.db.session import get_db
from kawach.repositories.audit_repo import AuditRepository
from kawach.services.export_service import export_run_zip, export_scripts_zip

router = APIRouter(tags=["exports"])


@router.get("/runs/{run_id}/export")
@router.get("/runs/{run_id}/tests/export")
@router.get("/runs/{run_id}/report/export")
def export_passing_tests(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export passing tests as a standalone runnable Playwright project."""
    AuditRepository(db).record(
        action="export",
        user_id=current_user.id,
        details={"run_id": run_id, "kind": "passing_tests"},
    )
    try:
        zip_buf = export_scripts_zip(run_id)
        filename = f"{run_id}-passing-tests.zip"
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError:
        # Fallback to export entire run directory if no passed tests
        zip_buf = export_run_zip(run_id)
        filename = f"{run_id}-export.zip"
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")


@router.get("/runs/{run_id}/export/scripts")
def export_scripts_only(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export passing test scripts as standalone Playwright project."""
    AuditRepository(db).record(
        action="export",
        user_id=current_user.id,
        details={"run_id": run_id, "kind": "scripts_only"},
    )
    try:
        zip_buf = export_scripts_zip(run_id)
        filename = f"{run_id}-passing-tests.zip"
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
