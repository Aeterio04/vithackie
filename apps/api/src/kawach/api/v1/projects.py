"""Project endpoints under strict multi-tenant ownership access control."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    targetUrl: str
    slug: Optional[str] = None
    description: Optional[str] = None
    defaultMode: str = "manual"
    budgets: Optional[Dict[str, Any]] = None
    allowedHosts: Optional[List[str]] = None


class UpdateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = None
    targetUrl: Optional[str] = None
    description: Optional[str] = None
    defaultMode: Optional[str] = None
    budgets: Optional[Dict[str, Any]] = None


class SetCredentialsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str
    password: str


def format_project_response(project: Project) -> Dict[str, Any]:
    """Format Project ORM model to camelCase wire schema."""
    return {
        "id": project.id,
        "ownerId": project.owner_id,
        "name": project.name,
        "slug": project.slug,
        "targetUrl": project.target_url,
        "description": project.description,
        "defaultMode": project.default_mode,
        "budgets": project.budgets or {},
        "allowedHosts": project.allowed_hosts or [],
        "specVersion": project.spec_version,
        "createdAt": project.created_at.isoformat() if project.created_at else None,
        "updatedAt": project.updated_at.isoformat() if project.updated_at else None,
        "archivedAt": project.archived_at.isoformat() if project.archived_at else None,
    }


@router.get("", response_model=List[Dict[str, Any]])
def list_projects(
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    _user: User = Depends(require_scope("runs:read")),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """List all projects owned by the authenticated user with pagination."""
    service = ProjectService(db)
    projects = service.list_projects(scope)
    return [format_project_response(p) for p in projects[offset : offset + limit]]



@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: CreateProjectRequest,
    _user: User = Depends(require_scope("runs:write")),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """Create a new project owned by current user."""
    service = ProjectService(db)
    try:
        project = service.create_project(
            scope=scope,
            name=payload.name,
            target_url=payload.targetUrl,
            slug=payload.slug,
            description=payload.description,
            default_mode=payload.defaultMode,
            budgets=payload.budgets,
            allowed_hosts=payload.allowedHosts,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return format_project_response(project)


@router.get("/{project_id}")
def get_project(
    _user: User = Depends(require_scope("runs:read")),
    project: Project = Depends(get_owned_project),
):
    """Get project details. Returns 404 if project is not owned by user."""
    return format_project_response(project)


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
    service = ProjectService(db)
    updated = service.update_project(
        scope=scope,
        project_id=project.id,
        name=payload.name,
        target_url=payload.targetUrl,
        description=payload.description,
        default_mode=payload.defaultMode,
        budgets=payload.budgets,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return format_project_response(updated)


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    _user: User = Depends(require_scope("runs:write")),
    project: Project = Depends(get_owned_project),
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """Soft-delete project."""
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
