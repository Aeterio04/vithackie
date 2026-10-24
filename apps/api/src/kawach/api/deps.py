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

from kawach.core.config import settings
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
from kawach.services.token_service import ApiTokenService

logger = logging.getLogger("kawach.api.deps")
bearer_scheme = HTTPBearer(auto_error=False)


def get_token_from_request(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[str]:
    """Extract the token from `Authorization: Bearer` or the httpOnly session cookie.

    A `?token=` query parameter is deliberately NOT accepted: URLs end up in logs and browser history.
    Browsers' EventSource sends the cookie, and non-browser clients can set the Bearer header."""
    if auth_header and auth_header.credentials:
        return auth_header.credentials

    # Check cookies
    for cookie_name in ("auth_token", "access_token", "token", "session", "kawach_session"):
        val = request.cookies.get(cookie_name)
        if val:
            return val

    return None


class AuthContext:
    """Authentication context tracking identity, client door, and granular permissions."""

    def __init__(
        self,
        user: User,
        client_type: str,
        scopes: set[str],
        is_session: bool,
        token_id: Optional[str] = None,
    ):
        self.user = user
        self.client_type = client_type
        self.scopes = scopes
        self.is_session = is_session
        self.token_id = token_id


ALL_SCOPES = [
    "runs:read",
    "runs:write",
    "tests:read",
    "tests:write",
    "fixes:apply",
    "tokens:admin",
]


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a Bearer token or session cookie; 401 otherwise."""
    auth_service = AuthService(db)

    if token:
        # 1. API Token authentication (MCP and CLI clients: kw_live_...)
        if token.startswith("kw_"):
            token_svc = ApiTokenService(db)
            res = token_svc.verify_token(token)
            if not res:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid, expired, or revoked API token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user, token_scopes, token_id = res
            request.state.auth_context = AuthContext(
                user=user,
                client_type="mcp",
                scopes=set(token_scopes),
                is_session=False,
                token_id=token_id,
            )
            return user

        # 2. JWT Access Token authentication (Web sessions)
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
        # Web sessions possess full operational scopes and interactive session privileges
        request.state.auth_context = AuthContext(
            user=user,
            client_type="web",
            scopes={"*", *ALL_SCOPES},
            is_session=True,
            token_id=None,
        )
        return user

    # No credentials: never fall back to a shared/default account.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_required(
    request: Request,
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
    return get_current_user(request=request, token=token, db=db)


def get_optional_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Resolve current user if credentials are provided; return None if unauthenticated."""
    if not token:
        return None
    try:
        return get_current_user(request=request, token=token, db=db)
    except HTTPException:
        return None


def get_client_type(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
) -> str:
    """Identify which front door is making the request: 'web' | 'github' | 'mcp'."""
    auth_ctx: Optional[AuthContext] = getattr(request.state, "auth_context", None)
    if auth_ctx:
        return auth_ctx.client_type
    if request.headers.get("x-github-event") or request.headers.get("x-hub-signature-256"):
        return "github"
    if token and token.startswith("kw_"):
        return "mcp"
    if request.headers.get("x-client-type") == "mcp":
        return "mcp"
    return "web"


def require_scope(*required_scopes: str):
    """Dependency factory checking that caller has at least one of the required scopes."""

    def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        auth_ctx: Optional[AuthContext] = getattr(request.state, "auth_context", None)
        if not auth_ctx:
            return current_user

        if "*" in auth_ctx.scopes:
            return current_user

        has_permission = any(scope in auth_ctx.scopes for scope in required_scopes)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: requires one of {list(required_scopes)}",
            )
        return current_user

    return dependency


def require_session_auth(
    request: Request,
    current_user: User = Depends(get_current_user_required),
) -> User:
    """Ensure endpoint is accessed via an interactive user session (JWT), never via API token."""
    auth_ctx: Optional[AuthContext] = getattr(request.state, "auth_context", None)
    if auth_ctx and not auth_ctx.is_session:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token management requires an interactive user session",
        )
    return current_user


def get_user_scope(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> Scope:
    """Generate multi-tenant repository Scope from current authenticated user."""
    # Request scopes are ALWAYS per-user. Cross-tenant "system" scope exists only for internal background code
    # (Scope.system()) and can never be obtained through an email address or a token.
    return Scope(user_id=current_user.id, is_system=False)


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

    # Not owned by this user (foreign, unknown, or an unclaimed pre-accounts run): 404, never auto-claimed.
    # Unclaimed legacy runs are assigned to a real account with scripts/claim_legacy_data.py.
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
