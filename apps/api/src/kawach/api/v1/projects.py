"""Project endpoints under strict multi-tenant ownership access control."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from kawach.api.deps import get_owned_project, get_user_scope, require_scope
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.db.session import get_db
from kawach.repositories.base import Scope
from kawach.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    targetUrl: Optional[str] = None
    testUrl: Optional[str] = None
    githubUrl: Optional[str] = None
    pat: Optional[str] = None
    workspaceId: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    defaultMode: str = "manual"
    budgets: Optional[Dict[str, Any]] = None
    allowedHosts: Optional[List[str]] = None


class UpdateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = None
    targetUrl: Optional[str] = None
    testUrl: Optional[str] = None
    githubUrl: Optional[str] = None
    pat: Optional[str] = None
    description: Optional[str] = None
    defaultMode: Optional[str] = None
    budgets: Optional[Dict[str, Any]] = None


class SetCredentialsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str
    password: str


def format_project_response(project: Project, db: Optional[Session] = None) -> Dict[str, Any]:
    """Format Project ORM model to camelCase wire schema."""
    from kawach.core.security import secret_store

    pat_masked = ""
    if project.pat_encrypted:
        try:
            decrypted = secret_store.decrypt(project.pat_encrypted)
            pat_masked = secret_store.mask_token(decrypted)
        except Exception:
            pat_masked = "••••••••"

    last_run_status = None
    saved_test_count = 0

    if db is not None:
        try:
            from kawach.db.models.runs import Run as DbRun
            from kawach.db.models.saved_tests import SavedTest
            from kawach.api.v1.mappers.run_mapper import map_stage_to_status

            latest_run = (
                db.query(DbRun)
                .filter(DbRun.project_id == project.id)
                .order_by(DbRun.created_at.desc())
                .first()
            )
            if latest_run:
                try:
                    from kawach.storage import artifacts as storage
                    r_disk = storage.read_json(latest_run.id, "run.json")
                    if r_disk and r_disk.get("stage") and latest_run.stage != r_disk["stage"]:
                        latest_run.stage = r_disk["stage"]
                        db.commit()
                except Exception:
                    pass
                last_run_status = map_stage_to_status(latest_run.stage)

            saved_test_count = (
                db.query(SavedTest)
                .filter(SavedTest.project_id == project.id, SavedTest.is_active == True)
                .count()
            )
            if saved_test_count == 0:
                try:
                    from kawach.services.saved_test_service import SavedTestService
                    SavedTestService(db).sync_project_runs(project.id)
                    saved_test_count = (
                        db.query(SavedTest)
                        .filter(SavedTest.project_id == project.id, SavedTest.is_active == True)
                        .count()
                    )
                except Exception:
                    pass
        except Exception:
            pass

    return {
        "id": project.id,
        "ownerId": project.owner_id,
        "userId": project.owner_id,
        "user_id": project.owner_id,
        "workspaceId": project.workspace_id,
        "workspace_id": project.workspace_id,
        "name": project.name,
        "slug": project.slug,
        "targetUrl": project.target_url,
        "testUrl": project.target_url,
        "test_url": project.target_url,
        "githubUrl": project.github_url or "",
        "github_url": project.github_url or "",
        "patMasked": pat_masked,
        "hasPat": bool(project.pat_encrypted),
        "description": project.description,
        "defaultMode": project.default_mode,
        "budgets": project.budgets or {},
        "allowedHosts": project.allowed_hosts or [],
        "specVersion": project.spec_version,
        "lastRunStatus": last_run_status,
        "savedTestCount": saved_test_count,
        "createdAt": project.created_at.isoformat() if project.created_at else None,
        "updatedAt": project.updated_at.isoformat() if project.updated_at else None,
        "archivedAt": project.archived_at.isoformat() if project.archived_at else None,
    }


@router.get("", response_model=List[Dict[str, Any]])
def list_projects(
    _user: User = Depends(require_scope("runs:read")),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """List all projects owned by the authenticated user."""
    service = ProjectService(db)
    projects = service.list_projects(scope)
    return [format_project_response(p, db=db) for p in projects]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: CreateProjectRequest,
    _user: User = Depends(require_scope("runs:write")),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """Create a new project owned by current user."""
    from kawach.core.security import secret_store
    service = ProjectService(db)

    target_url = (payload.targetUrl or payload.testUrl or "").strip()
    if not target_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="targetUrl or testUrl is required",
        )

    pat_encrypted = None
    if payload.pat and payload.pat.strip():
        pat_encrypted = secret_store.encrypt(payload.pat.strip())

    try:
        project = service.create_project(
            scope=scope,
            name=payload.name,
            target_url=target_url,
            slug=payload.slug,
            description=payload.description,
            default_mode=payload.defaultMode,
            budgets=payload.budgets,
            allowed_hosts=payload.allowedHosts,
            workspace_id=payload.workspaceId,
            github_url=payload.githubUrl.strip() if payload.githubUrl else None,
            pat_encrypted=pat_encrypted,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return format_project_response(project, db=db)


@router.get("/{project_id}")
def get_project(
    _user: User = Depends(require_scope("runs:read")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Get project details. Returns 404 if project is not owned by user."""
    return format_project_response(project, db=db)


@router.put("/{project_id}")
def update_project(
    project_id: str,
    payload: UpdateProjectRequest,
    _user: User = Depends(require_scope("runs:write")),
    project: Project = Depends(get_owned_project),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """Update owned project attributes."""
    from kawach.core.security import secret_store
    service = ProjectService(db)

    target_url = (payload.targetUrl or payload.testUrl or "").strip() or None
    pat_encrypted = None
    if payload.pat and payload.pat.strip():
        pat_encrypted = secret_store.encrypt(payload.pat.strip())

    updated = service.update_project(
        scope=scope,
        project_id=project.id,
        name=payload.name,
        target_url=target_url,
        description=payload.description,
        default_mode=payload.defaultMode,
        budgets=payload.budgets,
        github_url=payload.githubUrl.strip() if payload.githubUrl is not None else None,
        pat_encrypted=pat_encrypted,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return format_project_response(updated, db=db)


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    _user: User = Depends(require_scope("runs:write")),
    project: Project = Depends(get_owned_project),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """Delete project."""
    service = ProjectService(db)
    service.archive_project(scope, project.id)
    return {"ok": True}


@router.put("/{project_id}/credentials")
def set_credentials(
    project_id: str,
    payload: SetCredentialsRequest,
    _user: User = Depends(require_scope("runs:write")),
    project: Project = Depends(get_owned_project),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """Set encrypted target application credentials. Write-only: password is never returned."""
    service = ProjectService(db)
    res = service.set_credentials(
        scope=scope,
        project_id=project.id,
        username=payload.username,
        password=payload.password,
    )
    return res


@router.get("/{project_id}/credentials")
def get_credentials_info(
    project_id: str,
    _user: User = Depends(require_scope("runs:read")),
    project: Project = Depends(get_owned_project),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """Check credentials presence without revealing secret."""
    service = ProjectService(db)
    return service.get_credentials_info(scope, project.id)
