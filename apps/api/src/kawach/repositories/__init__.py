"""Repositories package exporting scoped data access abstractions."""

from kawach.repositories.base import BaseRepository, Scope
from kawach.repositories.project_repo import ProjectRepository
from kawach.repositories.run_repo import RunRepository
from kawach.repositories.test_repo import TestCatalogRepository
from kawach.repositories.bug_repo import BugRepository
from kawach.repositories.artifact_repo import ArtifactRepository
from kawach.repositories.user_repo import UserRepository
from kawach.repositories.audit_repo import AuditRepository

__all__ = [
    "BaseRepository",
    "Scope",
    "ProjectRepository",
    "RunRepository",
    "TestCatalogRepository",
    "BugRepository",
    "ArtifactRepository",
    "UserRepository",
    "AuditRepository",
]
