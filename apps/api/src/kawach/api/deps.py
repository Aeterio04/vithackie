"""FastAPI dependencies for database sessions, authentication, and multi-tenant resource ownership.

In accordance with Section 7:
- Ownership resolves through projects.
- Access to foreign resources returns 404 Not Found to prevent leaking existence.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.db.models.artifacts import Artifact
from kawach.db.models.bugs import Bug
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.db.models.runs import Run
from kawach.db.session import get_db
from kawach.repositories.artifact_repo import ArtifactRepository
from kawach.repositories.base import Scope
from kawach.repositories.bug_repo import BugRepository
from kawach.repositories.project_repo import ProjectRepository
from kawach.repositories.run_repo import RunRepository
from kawach.repositories.user_repo import UserRepository
from kawach.services.auth_service import AuthService

logger = logging.getLogger("kawach.api.deps")
bearer_scheme = HTTPBearer(auto_error=False)


def get_token_from_request(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    query_token: Optional[str] = Query(None, alias="token"),
) -> Optional[str]:
    """Extract bearer or cookie token from HTTP request or SSE query param."""
    if auth_header and auth_header.credentials:
        return auth_header.credentials

    # Check cookies
    for cookie_name in ("auth_token", "access_token", "token", "session", "kawach_session"):
        val = request.cookies.get(cookie_name)
        if val:
            return val

    # SSE EventSource browser fallback query parameter
    if query_token:
        return query_token

    return None


def get_current_user(
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db),
) -> User:
    """Resolve current user from token, falling back to system demo user if unauthenticated."""
    auth_service = AuthService(db)

    if token:
        payload = auth_service.verify_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = payload.get("sub")
        user = db.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account inactive or not found",
            )
        return user

    # Fallback to system demo user for local test suite and unauthenticated CLI requests
    system_user = db.scalar(select(User).where(User.email == "system@kawach.local"))
    if system_user:
        return system_user

    # Auto-create system user on first unauthenticated boot
    user_repo = UserRepository(db)
    system_user = user_repo.create_user(
        email="system@kawach.local",
        password_hash="system_demo_hash",
        display_name="KAWACH System",
    )
    return system_user


def get_current_user_required(
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db),
) -> User:
    """Strict authentication dependency that always requires a valid token (raises 401)."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    auth_service = AuthService(db)
    payload = auth_service.verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or not found",
        )
    return user


def get_user_scope(current_user: User = Depends(get_current_user)) -> Scope:
    """Generate multi-tenant repository Scope from current authenticated user."""
    is_system = (current_user.email == "system@kawach.local")
    return Scope(user_id=current_user.id, is_system=is_system)


def get_owned_project(
    project_id: str,
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
) -> Project:
    """Load project owned by current user.
    
    Returns 404 Not Found (not 403) for foreign projects to prevent existence leakage.
    """
    repo = ProjectRepository(db)
    project = repo.get_project(scope, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def get_owned_run(
    run_id: str,
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
) -> Run:
    """Load run owned by current user.
    
    Returns 404 Not Found (not 403) for foreign runs to prevent existence leakage.
    """
    repo = RunRepository(db)
    run = repo.get_run(scope, run_id)
    if run:
        return run

    # If run is in database but owned by someone else, return 404
    foreign_run = db.get(Run, run_id)
    if foreign_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    # If run is a legacy flat-file run not yet in DB, allow access for system scope
    if scope.is_system:
        from kawach.storage import artifacts as storage
        rdir = storage.run_dir(run_id)
        if (rdir / "run.json").exists():
            return Run(id=run_id, project_id="legacy-demo", created_by="system")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")


def get_owned_bug(
    run_id: str,
    bug_id: str,
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
) -> Bug:
    """Load defect owned by current user.
    
    Returns 404 Not Found for foreign bugs.
    """
    repo = BugRepository(db)
    bug = repo.get_bug(scope, run_id, bug_id)
    if not bug:
        # Also check by primary key ID if human-readable key didn't match
        stmt = (
            select(Bug)
            .join(Project, Bug.project_id == Project.id)
            .where(Bug.id == bug_id)
        )
        if not scope.is_system:
            if not scope.user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bug not found")
            stmt = stmt.where(Project.owner_id == scope.user_id)
        bug = db.scalars(stmt).first()
    if not bug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bug not found")
    return bug


def get_owned_artifact(
    artifact_id: str,
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
) -> Artifact:
    """Load artifact metadata owned by current user.
    
    Returns 404 Not Found for foreign artifacts.
    """
    repo = ArtifactRepository(db)
    art = repo.get_artifact(scope, artifact_id)
    if not art:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return art
