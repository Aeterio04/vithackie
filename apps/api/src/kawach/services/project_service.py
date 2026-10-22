"""Project management and target application credential service.

Coordinates project lifecycle, specification versioning, credential encryption,
and audit logging under strict multi-tenant ownership boundaries.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from kawach.core.security import secret_store
from kawach.db.models.project import Project, ProjectCredential
from kawach.repositories.audit_repo import AuditRepository
from kawach.repositories.base import Scope
from kawach.repositories.project_repo import ProjectRepository

logger = logging.getLogger("kawach.services.project")


class ProjectService:
    """Project domain service orchestrating scoped repository access."""

    def __init__(self, db: Session):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.audit_repo = AuditRepository(db)

    def create_project(
        self,
        scope: Scope,
        name: str,
        target_url: str,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        default_mode: str = "manual",
        budgets: Optional[Dict[str, Any]] = None,
        allowed_hosts: Optional[List[str]] = None,
    ) -> Project:
        """Create a new project owned by the scoped user."""
        if not name or not name.strip():
            raise ValueError("Project name is required")
        if not target_url or not target_url.strip():
            raise ValueError("Target application URL is required")

        project = self.project_repo.create_project(
            scope=scope,
            name=name.strip(),
            target_url=target_url.strip(),
            slug=slug,
            description=description,
            default_mode=default_mode,
            budgets=budgets,
            allowed_hosts=allowed_hosts,
        )

        self.audit_repo.record(
            action="project_create",
            user_id=scope.user_id,
            project_id=project.id,
            details={"name": project.name, "target_url": project.target_url},
        )
        return project

    def get_project(self, scope: Scope, project_id: str) -> Optional[Project]:
        """Retrieve project if owned by scope, else return None (leaks no existence)."""
        return self.project_repo.get_project(scope, project_id)

    def list_projects(self, scope: Scope) -> List[Project]:
        """List all active projects owned by scoped user."""
        return self.project_repo.list_projects(scope)

    def update_project(
        self,
        scope: Scope,
        project_id: str,
        name: Optional[str] = None,
        target_url: Optional[str] = None,
        description: Optional[str] = None,
        default_mode: Optional[str] = None,
        budgets: Optional[Dict[str, Any]] = None,
    ) -> Optional[Project]:
        """Update owned project properties."""
        project = self.project_repo.update_project(
            scope=scope,
            project_id=project_id,
            name=name,
            target_url=target_url,
            description=description,
            default_mode=default_mode,
            budgets=budgets,
        )
        if project:
            self.audit_repo.record(
                action="project_update",
                user_id=scope.user_id,
                project_id=project.id,
                details={"name": project.name},
            )
        return project

    def archive_project(self, scope: Scope, project_id: str) -> bool:
        """Soft-delete/archive project owned by scoped user."""
        success = self.project_repo.archive_project(scope, project_id)
        if success:
            self.audit_repo.record(
                action="project_delete",
                user_id=scope.user_id,
                project_id=project_id,
                details={"archived": True},
            )
        return success

    def set_credentials(
        self,
        scope: Scope,
        project_id: str,
        username: str,
        password: str,
    ) -> Dict[str, Any]:
        """Encrypt and save target app credentials at rest.
        
        Never returns or logs plaintext password.
        """
        project = self.get_project(scope, project_id)
        if not project:
            raise ValueError("Project not found")

        self.project_repo.set_credentials(
            scope=scope,
            project_id=project_id,
            username=username,
            password_plaintext=password,
        )

        self.audit_repo.record(
            action="credential_change",
            user_id=scope.user_id,
            project_id=project_id,
            details={"username": username, "hasSecret": True},
        )
        return {"hasSecret": True, "username": username}

    def get_credentials_info(self, scope: Scope, project_id: str) -> Dict[str, Any]:
        """Check credentials status without leaking secret."""
        project = self.get_project(scope, project_id)
        if not project:
            raise ValueError("Project not found")

        creds = self.project_repo.get_credentials(scope, project_id)
        if not creds:
            return {"hasSecret": False, "username": ""}
        username = creds[0] if isinstance(creds, tuple) else creds.username
        return {"hasSecret": True, "username": username}
