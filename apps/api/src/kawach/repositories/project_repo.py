"""Project repository for scoped multi-tenant project and credential data access."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.core.security import secret_store
from kawach.db.models import Project, ProjectCredential, SpecItem
from kawach.repositories.base import BaseRepository, Scope


class ProjectRepository(BaseRepository):
    """Data access methods for projects, specs, and credentials."""

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
        workspace_id: Optional[str] = None,
        github_url: Optional[str] = None,
        pat_encrypted: Optional[str] = None,
    ) -> Project:
        """Create a new project owned by scope.user_id."""
        import re
        owner_id = scope.user_id or "system"
        clean_slug = slug or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
        project = Project(
            owner_id=owner_id,
            workspace_id=workspace_id,
            name=name,
            slug=clean_slug,
            target_url=target_url,
            github_url=github_url,
            pat_encrypted=pat_encrypted,
            description=description,
            default_mode=default_mode,
            budgets=budgets or {},
            allowed_hosts=allowed_hosts or [],
        )
        self.db.add(project)
        self.db.flush()
        return project

    def get_project(self, scope: Scope, project_id: str) -> Optional[Project]:
        """Fetch project ensuring ownership isolation."""
        stmt = select(Project).where(Project.id == project_id)
        if not scope.is_system:
            if not scope.user_id:
                return None
            stmt = stmt.where(Project.owner_id == scope.user_id)
        return self.db.scalars(stmt).first()

    def get_project_by_slug(self, scope: Scope, slug: str) -> Optional[Project]:
        """Fetch project by slug within user's scope."""
        stmt = select(Project).where(Project.slug == slug)
        if not scope.is_system:
            if not scope.user_id:
                return None
            stmt = stmt.where(Project.owner_id == scope.user_id)
        return self.db.scalars(stmt).first()

    def list_projects(self, scope: Scope, include_archived: bool = False) -> List[Project]:
        """List all projects owned by the user."""
        stmt = select(Project)
        if not scope.is_system:
            if not scope.user_id:
                return []
            stmt = stmt.where(Project.owner_id == scope.user_id)
        if not include_archived:
            stmt = stmt.where(Project.archived_at.is_(None))
        stmt = stmt.order_by(Project.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def update_project(
        self,
        scope: Scope,
        project_id: str,
        name: Optional[str] = None,
        target_url: Optional[str] = None,
        description: Optional[str] = None,
        default_mode: Optional[str] = None,
        budgets: Optional[Dict[str, Any]] = None,
        github_url: Optional[str] = None,
        pat_encrypted: Optional[str] = None,
    ) -> Optional[Project]:
        """Update owned project attributes."""
        project = self.get_project(scope, project_id)
        if not project:
            return None
        if name is not None:
            project.name = name
        if target_url is not None:
            project.target_url = target_url
        if description is not None:
            project.description = description
        if default_mode is not None:
            project.default_mode = default_mode
        if budgets is not None:
            project.budgets = budgets
        if github_url is not None:
            project.github_url = github_url
        if pat_encrypted is not None:
            project.pat_encrypted = pat_encrypted
        self.db.flush()
        return project

    def archive_project(self, scope: Scope, project_id: str) -> bool:
        """Soft-delete/archive project owned by scoped user."""
        project = self.get_project(scope, project_id)
        if not project:
            return False
        project.archived_at = datetime.now(timezone.utc)
        self.db.flush()
        return True

    def set_credentials(
        self,
        scope: Scope,
        project_id: str,
        username: str,
        password_plaintext: str,
    ) -> ProjectCredential:
        """Store encrypted credentials for a project."""
        project = self.get_project(scope, project_id)
        if not project:
            raise ValueError("Project not found or not owned by user")

        encrypted_secret = secret_store.encrypt(password_plaintext)
        cred = self.db.get(ProjectCredential, project_id)
        if cred:
            cred.username = username
            cred.secret_ciphertext = encrypted_secret
        else:
            cred = ProjectCredential(
                project_id=project_id,
                username=username,
                secret_ciphertext=encrypted_secret,
            )
            self.db.add(cred)
        self.db.flush()
        return cred

    def get_credentials(
        self,
        scope: Scope,
        project_id: str,
    ) -> Optional[Tuple_Creds]:
        """Return decrypted credentials tuple (username, plaintext_password) if owned."""
        project = self.get_project(scope, project_id)
        if not project:
            return None
        cred = self.db.get(ProjectCredential, project_id)
        if not cred:
            return None
        return cred.username, secret_store.decrypt(cred.secret_ciphertext)

    def save_spec_items(
        self,
        scope: Scope,
        project_id: str,
        spec_items: List[Dict[str, Any]],
        spec_version: int = 1,
    ) -> List[SpecItem]:
        """Persist parsed spec items for a project version."""
        project = self.get_project(scope, project_id)
        if not project:
            raise ValueError("Project not found or not owned by user")

        results = []
        for idx, item in enumerate(spec_items):
            spec_obj = SpecItem(
                project_id=project_id,
                spec_version=spec_version,
                key=item.get("id") or f"S{idx+1}",
                text=item.get("text", ""),
                position=idx,
            )
            self.db.add(spec_obj)
            results.append(spec_obj)
        project.spec_version = spec_version
        self.db.flush()
        return results

    def get_spec_items(self, scope: Scope, project_id: str) -> List[SpecItem]:
        """Get spec items for active project version."""
        project = self.get_project(scope, project_id)
        if not project:
            return []
        stmt = (
            select(SpecItem)
            .where(SpecItem.project_id == project_id, SpecItem.spec_version == project.spec_version)
            .order_by(SpecItem.position.asc())
        )
        return list(self.db.scalars(stmt).all())


Tuple_Creds = tuple[str, str]
