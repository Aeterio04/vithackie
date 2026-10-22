"""Artifact metadata repository with owner isolation."""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.db.models import Artifact, Project
from kawach.repositories.base import BaseRepository, Scope


class ArtifactRepository(BaseRepository):
    """Scoped repository for artifact metadata records."""

    def create_artifact(
        self,
        scope: Scope,
        project_id: str,
        kind: str,
        uri: str,
        size_bytes: int,
        mime: Optional[str] = None,
        sha256: Optional[str] = None,
        run_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
    ) -> Artifact:
        """Register artifact record in database."""
        artifact = Artifact(
            id=artifact_id or None,
            project_id=project_id,
            run_id=run_id,
            kind=kind,
            uri=uri,
            mime=mime,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def get_artifact(self, scope: Scope, artifact_id: str) -> Optional[Artifact]:
        """Fetch artifact ensuring caller owns the parent project."""
        stmt = (
            select(Artifact)
            .join(Project, Artifact.project_id == Project.id)
            .where(Artifact.id == artifact_id)
        )
        if not scope.is_system:
            if not scope.user_id:
                return None
            stmt = stmt.where(Project.owner_id == scope.user_id)
        return self.db.scalars(stmt).first()

    def list_artifacts_for_run(self, scope: Scope, run_id: str) -> List[Artifact]:
        """List all artifacts associated with a run."""
        stmt = (
            select(Artifact)
            .join(Project, Artifact.project_id == Project.id)
            .where(Artifact.run_id == run_id)
        )
        if not scope.is_system:
            if not scope.user_id:
                return []
            stmt = stmt.where(Project.owner_id == scope.user_id)
        return list(self.db.scalars(stmt).all())
