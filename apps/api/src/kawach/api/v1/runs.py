from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session

from kawach.api.deps import get_current_user, get_owned_project, get_owned_run, get_user_scope, require_scope
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
from kawach.services.run_service import SpecAlignmentError, compute_alignment
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
    project_id: Optional[str] = None,
    projectId: Optional[str] = None,
    _user: User = Depends(require_scope("runs:read")),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """List test runs scoped to the authenticated user, optionally filtered by project."""
    target_project_id = project_id or projectId
    all_runs = storage.list_runs()
    result = []
    run_repo = RunRepository(db)

    for r in all_runs:
        db_run = run_repo.get_run(scope, r.runId)
        # Check ownership
        if not scope.is_system:
            if not db_run:
                continue  # Skip runs not owned by current user
        if target_project_id and db_run and db_run.project_id != target_project_id:
            continue
        try:
            fe_run = transform_run_to_frontend(r.runId)
            if db_run:
                fe_run["projectId"] = db_run.project_id
                fe_run["project_id"] = db_run.project_id
                # Sync DB stage with actual stage
                if fe_run.get("stage") and db_run.stage != fe_run["stage"]:
                    db_run.stage = fe_run["stage"]
                    db.commit()
            result.append(fe_run)
        except Exception:
            continue
    return result


@router.get("/projects/{project_id}/runs")
def list_project_runs(
    project_id: str,
    _project=Depends(get_owned_project),  # 404 for another user's project
    _user: User = Depends(require_scope("runs:read")),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """List test runs for a specific project."""
    return list_runs(project_id=project_id, _user=_user, scope=scope, db=db)


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
    if payload.spec_id and UPLOADED_SPECS.get(payload.spec_id, {}).get("owner_id") == current_user.id:
        spec_raw = UPLOADED_SPECS[payload.spec_id]["content"]
    elif payload.spec_id and not payload.spec_text:
        raise HTTPException(status_code=404, detail="Spec not found")
    elif payload.spec_text and payload.spec_text.strip():
        spec_raw = payload.spec_text.strip()
    else:
        # Never inject alien spec files from other demo projects.
        # If no spec is provided, exploratory testing runs against universal web rules.
        spec_raw = ""

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

    # Determine project association strictly matching the target URL
    proj_repo = ProjectRepository(db)
    user_scope = Scope.user(current_user.id)
    proj_id = payload.project_id
    if proj_id and not proj_repo.get_project(user_scope, proj_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if not proj_id:
        user_projects = proj_repo.list_projects(user_scope, include_archived=True)
        norm_target = ProjectRepository.normalize_url(payload.target_url)
        matching = next(
            (p for p in user_projects if ProjectRepository.normalize_url(p.target_url) == norm_target),
            None,
        )
        if matching:
            proj_id = matching.id
            if matching.archived_at is not None:
                matching.archived_at = None
                db.flush()
        else:
            import urllib.parse
            parsed = urllib.parse.urlparse(payload.target_url)
            port_str = f":{parsed.port}" if parsed.port else ""
            parsed_host = f"{parsed.hostname or 'Target'}{port_str}"
            new_proj = proj_repo.create_project(
                scope=user_scope,
                name=f"{parsed_host} App",
                target_url=payload.target_url,
                default_mode=payload.review_mode or "manual",
            )
            proj_id = new_proj.id

    run = create_run_service(
        target_url=payload.target_url,
        mode=payload.review_mode,  # type: ignore
        prompt=payload.prompt,
        spec_raw=spec_raw,
        username=username,
        password=password,
        budgets=budgets,
        project_id=proj_id,
    )

    # Persist run in SQLite DB linked to user's project
    run_repo = RunRepository(db)
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
    tier: Optional[str] = None,
    _user: User = Depends(require_scope("runs:write")),
    _run: DbRun = Depends(get_owned_run),
):
    """Start or restart a run."""
    run = storage.load_model(run_id, "run.json", storage.Run)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        resume_run_service(run_id, tier=tier)
    except SpecAlignmentError as e:
        raise HTTPException(status_code=409, detail=f"Cannot start execution: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return transform_run_to_frontend(run_id)


@router.get("/runs/{run_id}/alignment")
def get_run_alignment(
    run_id: str,
    _user: User = Depends(require_scope("runs:read")),
    _run: DbRun = Depends(get_owned_run),
):
    """Spec vs catalog alignment (spec_driven runs only)."""
    report = compute_alignment(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Run is not spec-driven")
    return report


@router.get("/runs/{run_id}/budgets")
def get_run_budgets(
    run_id: str,
    tier: Optional[str] = None,
    _user: User = Depends(require_scope("runs:read")),
    _run: DbRun = Depends(get_owned_run),
):
    """Used vs needed time/pages per stage, suggested from the spec (spec-driven runs)."""
    from datetime import datetime

    from kawach.schemas import AppMap, RunInput
    from kawach.services.spec_budgets import estimate
    from kawach.services.spec_structured import has_test_case_blocks

    ri = storage.load_model(run_id, "input.json", RunInput)
    run = storage.load_model(run_id, "run.json", storage.Run)
    if not ri or not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not has_test_case_blocks(ri.specRaw or ""):
        raise HTTPException(status_code=404, detail="Run is not spec-driven")
    est = estimate(ri.specRaw, tier or ri.priorityTier)
    used = {}
    for name, st in run.stageTimes.items():
        try:
            a = datetime.fromisoformat(st.startedAt.replace("Z", "+00:00"))
            b = datetime.fromisoformat((st.endedAt or run.updatedAt).replace("Z", "+00:00"))
            used[name] = round((b - a).total_seconds(), 1)
        except Exception:
            pass
    need = est["stageSeconds"]
    stage_map = {"exploring": "explore", "planning": "plan", "scripting": "scripting", "running": "running", "reporting": "report"}
    stages = [
        {"stage": label, "usedSeconds": used.get(k), "neededSeconds": need[label],
         "overBudget": used.get(k) is not None and used[k] > need[label] * 1.25}
        for k, label in stage_map.items()
    ]
    app_map = storage.load_model(run_id, "app_map.json", AppMap)
    warnings = []
    if ri.budgets.maxPages < est["pagesNeeded"]:
        warnings.append(f"page budget {ri.budgets.maxPages} is lower than the {est['pagesNeeded']} URLs the spec needs; suggested {est['pagesBudget']}")
    return {
        "tier": est["tier"], "testsInTier": est["testsInTier"],
        "pages": {"used": len(app_map.pages) if app_map else 0, "needed": est["pagesNeeded"], "budget": ri.budgets.maxPages, "suggested": est["pagesBudget"]},
        "stages": stages, "suggestedTotalSeconds": est["totalSeconds"], "warnings": warnings,
    }


@router.post("/runs/{run_id}/resume")
def resume_run_endpoint(
    run_id: str,
    tier: Optional[str] = None,
    _user: User = Depends(require_scope("runs:write")),
    _run: DbRun = Depends(get_owned_run),
):
    """Resume execution of an approved test catalog."""
    try:
        resume_run_service(run_id, tier=tier)
        return transform_run_to_frontend(run_id)
    except SpecAlignmentError as e:
        raise HTTPException(status_code=409, detail=f"Cannot start execution: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
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
    resume_run_service(run_id, retry=True)
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

