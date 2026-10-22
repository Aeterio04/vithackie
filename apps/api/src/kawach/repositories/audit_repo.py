"""Audit trail repository for sensitive security actions."""

from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.db.models import AuditLog
from kawach.repositories.base import BaseRepository, Scope


class AuditRepository(BaseRepository):
    """Data access for security audit log entries."""

    def record(
        self,
        action: str,
        entity_type: str = "security",
        entity_id: Optional[str] = None,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
        ip: Optional[str] = None,
    ) -> AuditLog:
        """Create an immutable audit log record."""
        meta = metadata or details or {}
        log = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            project_id=project_id,
            metadata_json=meta,
            ip=ip,
        )
        self.db.add(log)
        self.db.commit()
        return log

    def list_audit_logs(
        self,
        scope: Scope,
        project_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditLog]:
        """List audit logs scoped to user or project."""
        stmt = select(AuditLog)
        if not scope.is_system:
            if not scope.user_id:
                return []
            stmt = stmt.where(AuditLog.user_id == scope.user_id)
        if project_id:
            stmt = stmt.where(AuditLog.project_id == project_id)
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())
