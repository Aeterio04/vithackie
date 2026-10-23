from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from kawach.api.deps import get_current_user, get_owned_run, get_user_scope, require_scope
from kawach.api.v1.config import UPLOADED_SPECS
from kawach.api.v1.mappers.run_mapper import transform_run_to_frontend
from kawach.core.config import settings
from kawach.db.models.identity import User
from kawach.db.models.runs import Run as DbRun
from kawach.db.session import get_db
from kawach.repositories.audit_repo import AuditRepository
from kawach.repositories.base import Scope
from kawach.repositories.run_repo import RunRepository
from kawach.schemas import Budgets
from kawach.services.idempotency import IdempotencyService
from kawach.services.run_service import cancel_run as cancel_run_service
from kawach.services.run_service import create_run as create_run_service
from kawach.services.run_service import delete_run as delete_run_service
from kawach.services.run_service import resume_run as resume_run_service
from kawach.storage import artifacts as storage

router = APIRouter(tags=["runs"])


class CreateRunPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target_url: str
    prompt: str = ""
    spec_id: Optional[str] = None
    spec_text: Optional[str] = None
    review_mode: str = "manual"
    budgets: Optional[Dict[str, Any]] = None
    credentials: Optional[Dict[str, Any]] = None


@router.get("/runs")
def list_runs(
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    status: Optional[str] = Query(None, description="Filter by run status/stage"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    _user: User = Depends(require_scope("runs:read")),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """List test runs scoped to the authenticated user with filtering and pagination."""
    all_runs = storage.list_runs()
    result = []
    run_repo = RunRepository(db)

    for r in all_runs:
        # Check ownership if run is in DB
        db_run = db.get(DbRun, r.runId)
        if db_run and not scope.is_system:
            if not run_repo.get_run(scope, r.runId):
                continue  # Skip runs owned by other tenants
        if project_id:
            if db_run and db_run.project_id != project_id:
                continue
        if status:
            stage_match = (db_run and db_run.stage == status) or (getattr(r, "stage", None) == status)
            if not stage_match:
                continue
        try:
            result.append(transform_run_to_frontend(r.runId))
        except Exception:
            continue
    return result[offset : offset + limit]



@router.post("/runs", status_code=status.HTTP_201_CREATED)
def create_run(
    payload: CreateRunPayload,
    current_user: User = Depends(require_scope("runs:write")),
    db: Session = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """Create a new QA test run and begin exploration/planning."""
    # 0. Check idempotency
    cached = IdempotencyService.check_or_record(
        user_id=current_user.id,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    if cached:
        status_code, response_data = cached
        return JSONResponse(status_code=status_code, content=response_data)

    spec_raw = ""
    if payload.spec_id and payload.spec_id in UPLOADED_SPECS:
        spec_raw = UPLOADED_SPECS[payload.spec_id]["content"]
    elif payload.spec_text and payload.spec_text.strip():
        spec_raw = payload.spec_text.strip()
    else:
        spec_file = settings.repo_root / "examples" / "target-app" / "spec.md"
        if not spec_file.exists():
            spec_file = settings.repo_root / "target-app" / "spec.md"
        if spec_file.exists():
            spec_raw = spec_file.read_text(encoding="utf-8")

    creds = payload.credentials or {}
    username = creds.get("username", "")
    password = creds.get("password", "")

    b_dict = payload.budgets or {}
    budgets = Budgets(
        maxPages=b_dict.get("max_pages", settings.MAX_PAGES),
        exploreSeconds=b_dict.get("explore_seconds", settings.EXPLORE_SECONDS),
        maxTests=b_dict.get("max_tests", settings.MAX_TESTS),
        testTimeoutMs=b_dict.get("test_timeout_ms", settings.TEST_TIMEOUT_MS),
    )

    run = create_run_service(
        target_url=payload.target_url,
        mode=payload.review_mode,  # type: ignore
        prompt=payload.prompt,
        spec_raw=spec_raw,
        username=username,
        password=password,
        budgets=budgets,
    )

    AuditRepository(db).record(
        action="run_start",
        user_id=current_user.id,
        details={"run_id": run.runId, "target_url": payload.target_url, "mode": payload.review_mode},
    )

    res = transform_run_to_frontend(run.runId)
    IdempotencyService.store_response(
        user_id=current_user.id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        response_data=res,
    )
    return res


@router.get("/runs/{run_id}")
def get_single_run(
    run_id: str,
    _user: User = Depends(require_scope("runs:read")),
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve detailed state of a single run. Returns 404 for foreign runs."""
    try:
        return transform_run_to_frontend(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")


@router.post("/runs/{run_id}/start")
def start_run_pipeline(
    run_id: str,
    _user: User = Depends(require_scope("runs:write")),
    _run: DbRun = Depends(get_owned_run),
):
    """Start or restart a run."""
    run = storage.load_model(run_id, "run.json", storage.Run)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    resume_run_service(run_id)
    return transform_run_to_frontend(run_id)


@router.post("/runs/{run_id}/resume")
@router.post("/runs/{run_id}/execute")
def resume_run_endpoint(
    run_id: str,
    _user: User = Depends(require_scope("runs:write")),
    _run: DbRun = Depends(get_owned_run),
):
    """Resume execution of an approved test catalog."""
    try:
        resume_run_service(run_id)
        return transform_run_to_frontend(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")


@router.post("/runs/{run_id}/cancel")
def cancel_run_endpoint(run_id: str):
    """Cancel an active run."""
    try:
        cancel_run_service(run_id)
        return transform_run_to_frontend(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")


@router.post("/runs/{run_id}/retry")
def retry_run(run_id: str):
    """Reset run state and retry execution."""
    run = storage.load_model(run_id, "run.json", storage.Run)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    resume_run_service(run_id)
    return transform_run_to_frontend(run_id)


@router.delete("/runs/{run_id}")
def delete_run_endpoint(run_id: str):
    """Delete run artifacts and remove from memory."""
    delete_run_service(run_id)
    return {"ok": True, "run_id": run_id}
