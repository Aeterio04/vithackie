"""Bug repository managing triaged defects, evidence attachments, and 3x replay trials."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.db.base import utc_now
from kawach.db.models import (
    Bug,
    BugDuplicate,
    BugEvidence,
    Project,
    Run,
    Verification,
    VerificationAttempt,
)
from kawach.repositories.base import BaseRepository, Scope


class BugRepository(BaseRepository):
    """Scoped repository for defect management and deterministic proving."""

    def save_bugs(
        self,
        scope: Scope,
        run_id: str,
        bugs: List[Dict[str, Any]],
    ) -> List[Bug]:
        """Save triaged bugs for a run."""
        stmt = select(Run).join(Project, Run.project_id == Project.id).where(Run.id == run_id)
        if not scope.is_system:
            if not scope.user_id:
                raise ValueError("Unauthorized")
            stmt = stmt.where(Project.owner_id == scope.user_id)
        run = self.db.scalars(stmt).first()
        if not run:
            raise ValueError(f"Run {run_id} not found or not owned by user")

        created_bugs = []
        for b in bugs:
            bug = Bug(
                project_id=run.project_id,
                run_id=run_id,
                key=b.get("id") or b.get("key"),
                test_case_id=b.get("testId") or b.get("test_case_id"),
                signature=b.get("signature"),
                fingerprint=b.get("fingerprint") or b.get("id"),
                title=b.get("title", ""),
                category=b.get("category", "functional"),
                severity=b.get("severity", "medium"),
                steps=b.get("steps", []),
                expected=b.get("expected"),
                actual=b.get("actual"),
                error_message=b.get("errorMessage"),
                status=b.get("status", "candidate"),
                first_seen_run_id=b.get("first_seen_run_id") or run_id,
            )
            self.db.add(bug)
            self.db.flush()

            for dup_id in b.get("duplicates", []):
                dup = BugDuplicate(bug_id=bug.id, duplicate_test_case_id=dup_id)
                self.db.add(dup)

            created_bugs.append(bug)

        self.db.flush()
        return created_bugs

    def get_bugs(self, scope: Scope, run_id: str) -> List[Bug]:
        """Fetch all bugs discovered in a run."""
        stmt = (
            select(Bug)
            .join(Project, Bug.project_id == Project.id)
            .where(Bug.run_id == run_id)
        )
        if not scope.is_system:
            if not scope.user_id:
                return []
            stmt = stmt.where(Project.owner_id == scope.user_id)
        stmt = stmt.order_by(Bug.key.asc())
        return list(self.db.scalars(stmt).all())

    def get_bug(self, scope: Scope, run_id: str, key: str) -> Optional[Bug]:
        """Fetch single defect by run and human-readable key (e.g. B01)."""
        stmt = (
            select(Bug)
            .join(Project, Bug.project_id == Project.id)
            .where(Bug.run_id == run_id, Bug.key == key)
        )
        if not scope.is_system:
            if not scope.user_id:
                return None
            stmt = stmt.where(Project.owner_id == scope.user_id)
        return self.db.scalars(stmt).first()

    def record_verification(
        self,
        scope: Scope,
        bug_id: str,
        kind: str,
        reproduced_count: int,
        attempts: List[Dict[str, Any]],
        status: str,
    ) -> Verification:
        """Record 3x clean replay verification outcome and individual attempt trials."""
        verif = Verification(
            bug_id=bug_id,
            kind=kind,
            reproduced_count=reproduced_count,
            attempts_total=len(attempts),
            status=status,
            verified_at=utc_now(),
        )
        self.db.add(verif)
        self.db.flush()

        for a in attempts:
            va = VerificationAttempt(
                verification_id=verif.id,
                attempt_no=a.get("attempt_no", 1),
                reproduced=a.get("reproduced", False),
                outcome=a.get("outcome", "passed"),
                duration_ms=int(a.get("durationMs", 0)),
                error_message=a.get("errorMessage"),
            )
            self.db.add(va)

        # Update bug status based on replay
        bug = self.db.get(Bug, bug_id)
        if bug:
            bug.status = status

        self.db.flush()
        return verif
