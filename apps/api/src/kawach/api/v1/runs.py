from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, model_validator
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
from kawach.repositories.project_repo import ProjectRepository
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
    target_url: Optional[str] = None
    targetUrl: Optional[str] = None
    prompt: str = ""
    spec_id: Optional[str] = None
    spec_text: Optional[str] = None
    review_mode: Optional[str] = "manual"
    reviewMode: Optional[str] = None
    project_id: Optional[str] = None
    projectId: Optional[str] = None
    budgets: Optional[Dict[str, Any]] = None
    credentials: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def normalize_fields(self) -> "CreateRunPayload":
        self.target_url = self.target_url or self.targetUrl
        self.review_mode = self.review_mode or self.reviewMode or "manual"
        self.project_id = self.project_id or self.projectId
        if not self.target_url:
            raise ValueError("target_url or targetUrl is required")
        return self


@router.get("/runs")
def list_runs(
    _user: User = Depends(require_scope("runs:read")),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """List test runs scoped to the authenticated user."""
    all_runs = storage.list_runs()
    result = []
    run_repo = RunRepository(db)

    for r in all_runs:
        # Check ownership
        if not scope.is_system:
            if not run_repo.get_run(scope, r.runId):
                continue  # Skip runs not owned by current user
        try:
            result.append(transform_run_to_frontend(r.runId))
        except Exception:
            continue
    return result


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

    # Persist run in SQLite DB linked to user's project
    run_repo = RunRepository(db)
    proj_repo = ProjectRepository(db)
    user_scope = Scope.user(current_user.id)
    proj_id = payload.project_id
    if not proj_id:
        user_projects = proj_repo.list_projects(user_scope)
        matching = next((p for p in user_projects if p.target_url == payload.target_url), None)
        if matching:
            proj_id = matching.id
        elif user_projects:
            proj_id = user_projects[0].id
        else:
            import urllib.parse
            parsed_host = urllib.parse.urlparse(payload.target_url).hostname or "Target"
            new_proj = proj_repo.create_project(
                scope=user_scope,
                name=f"{parsed_host} App",
                target_url=payload.target_url,
                default_mode=payload.review_mode or "manual",
            )
            proj_id = new_proj.id

    run_repo.create_run(
        scope=user_scope,
        run_id=run.runId,
        project_id=proj_id,
        mode=payload.review_mode or "manual",
    )
    db.commit()

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
def cancel_run_endpoint(
    run_id: str,
    _user: User = Depends(require_scope("runs:write")),
    _run: DbRun = Depends(get_owned_run),
):
    """Cancel an active run. Returns 404 if run is not owned by the caller."""
    try:
        cancel_run_service(run_id)
        return transform_run_to_frontend(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")


@router.post("/runs/{run_id}/retry")
def retry_run(
    run_id: str,
    _user: User = Depends(require_scope("runs:write")),
    _run: DbRun = Depends(get_owned_run),
):
    """Reset run state and retry execution. Returns 404 if run is not owned by the caller."""
    run = storage.load_model(run_id, "run.json", storage.Run)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    resume_run_service(run_id)
    return transform_run_to_frontend(run_id)


@router.delete("/runs/{run_id}")
def delete_run_endpoint(
    run_id: str,
    _user: User = Depends(require_scope("runs:write")),
    _run: DbRun = Depends(get_owned_run),
    db: Session = Depends(get_db),
):
    """Delete run artifacts and remove from memory. Returns 404 if run is not owned by the caller."""
    delete_run_service(run_id)

    # Clean up associated artifacts from disk and database
    from kawach.repositories.artifact_repo import ArtifactRepository
    from kawach.storage.file_storage import delete_artifact_file
    art_repo = ArtifactRepository(db)
    artifacts = art_repo.list_artifacts_for_run(Scope.system(), run_id)
    for art in artifacts:
        delete_artifact_file(art, db)

    db.delete(_run)
    db.commit()
    return {"ok": True, "run_id": run_id}

