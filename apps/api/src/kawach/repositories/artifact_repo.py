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
        project_id: Optional[str] = None,
        kind: str = "other",
        uri: str = "",
        size_bytes: int = 0,
        mime: Optional[str] = None,
        sha256: Optional[str] = None,
        run_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
        user_id: Optional[str] = None,
        test_id: Optional[str] = None,
        type: Optional[str] = None,
        relative_path: Optional[str] = None,
    ) -> Artifact:
        """Register artifact record in database."""
        effective_user_id = user_id or scope.user_id
        artifact = Artifact(
            id=artifact_id or None,
            user_id=effective_user_id,
            test_id=test_id or run_id,
            project_id=project_id,
            run_id=run_id or test_id,
            kind=kind,
            type=type or kind,
            uri=uri,
            relative_path=relative_path or uri,
            mime=mime,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def get_artifact(self, scope: Scope, artifact_id: str) -> Optional[Artifact]:
        """Fetch artifact ensuring caller owns the parent project or is artifact owner."""
        from sqlalchemy import or_
        stmt = (
            select(Artifact)
            .outerjoin(Project, Artifact.project_id == Project.id)
            .where(Artifact.id == artifact_id)
        )
        if not scope.is_system:
            if not scope.user_id:
                return None
            stmt = stmt.where(or_(Project.owner_id == scope.user_id, Artifact.user_id == scope.user_id))
        return self.db.scalars(stmt).first()

    def list_artifacts_for_run(self, scope: Scope, run_id: str) -> List[Artifact]:
        """List all artifacts associated with a run."""
        from sqlalchemy import or_
        stmt = (
            select(Artifact)
            .outerjoin(Project, Artifact.project_id == Project.id)
            .where(Artifact.run_id == run_id)
        )
        if not scope.is_system:
            if not scope.user_id:
                return []
            stmt = stmt.where(or_(Project.owner_id == scope.user_id, Artifact.user_id == scope.user_id))
        return list(self.db.scalars(stmt).all())

