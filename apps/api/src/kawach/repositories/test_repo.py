"""Test catalog, scripts, review decisions, and test results repository."""

from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.db.models import (
    Project,
    ReviewDecision,
    Run,
    SpecItem,
    TestCase,
    TestCaseSpecRef,
    TestResult,
    TestScript,
)
from kawach.repositories.base import BaseRepository, Scope


class TestCatalogRepository(BaseRepository):
    """Scoped repository for test catalog generation, review, scripts, and outcomes."""

    def save_catalog(
        self,
        scope: Scope,
        run_id: str,
        tests: List[Dict[str, Any]],
    ) -> List[TestCase]:
        """Save planned test cases and link spec items."""
        stmt = select(Run).join(Project, Run.project_id == Project.id).where(Run.id == run_id)
        if not scope.is_system:
            if not scope.user_id:
                raise ValueError("Unauthorized")
            stmt = stmt.where(Project.owner_id == scope.user_id)
        run = self.db.scalars(stmt).first()
        if not run:
            raise ValueError(f"Run {run_id} not found or not owned by user")

        # Map existing spec items for the project
        spec_stmt = select(SpecItem).where(SpecItem.project_id == run.project_id)
        spec_items_map = {item.key: item.id for item in self.db.scalars(spec_stmt).all()}

        created_cases = []
        for t in tests:
            tc = TestCase(
                project_id=run.project_id,
                run_id=run_id,
                key=t.get("id") or t.get("key"),
                title=t.get("title", ""),
                description=t.get("description"),
                priority=t.get("priority", "medium"),
                status=t.get("status", "proposed"),
                origin=t.get("origin", "planned"),
                steps=t.get("steps", []),
            )
            self.db.add(tc)
            self.db.flush()

            # Spec refs
            for spec_key in t.get("specRef", []):
                spec_id = spec_items_map.get(spec_key)
                if spec_id:
                    ref = TestCaseSpecRef(
                        test_case_id=tc.id,
                        spec_item_id=spec_id,
                    )
                    self.db.add(ref)
            created_cases.append(tc)

        self.db.flush()
        return created_cases

    def get_catalog(self, scope: Scope, run_id: str) -> List[TestCase]:
        """Fetch all test cases for a run."""
        stmt = (
            select(TestCase)
            .join(Project, TestCase.project_id == Project.id)
            .where(TestCase.run_id == run_id)
        )
        if not scope.is_system:
            if not scope.user_id:
                return []
            stmt = stmt.where(Project.owner_id == scope.user_id)
        stmt = stmt.order_by(TestCase.key.asc())
        return list(self.db.scalars(stmt).all())

    def update_test_status(
        self,
        scope: Scope,
        run_id: str,
        test_key: str,
        status: str,
        reason: Optional[str] = None,
        reviewer_kind: str = "human",
    ) -> Optional[TestCase]:
        """Update test approval status and record a review decision."""
        stmt = (
            select(TestCase)
            .join(Project, TestCase.project_id == Project.id)
            .where(TestCase.run_id == run_id, TestCase.key == test_key)
        )
        if not scope.is_system:
            if not scope.user_id:
                return None
            stmt = stmt.where(Project.owner_id == scope.user_id)
        tc = self.db.scalars(stmt).first()
        if not tc:
            return None

        tc.status = status
        decision = ReviewDecision(
            run_id=run_id,
            test_case_id=tc.id,
            decision=status,
            reason=reason,
            reviewer_kind=reviewer_kind,
            reviewer_user_id=scope.user_id,
        )
        self.db.add(decision)
        self.db.flush()
        return tc

    def save_script(
        self,
        test_case_id: str,
        artifact_id: Optional[str] = None,
        version: int = 1,
        content_hash: Optional[str] = None,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> TestScript:
        """Record a test script associated with a test case."""
        script = TestScript(
            test_case_id=test_case_id,
            artifact_id=artifact_id,
            version=version,
            content_hash=content_hash,
            status=status,
            error=error,
        )
        self.db.add(script)
        self.db.flush()
        return script

    def save_results(
        self,
        scope: Scope,
        run_id: str,
        results: List[Dict[str, Any]],
    ) -> List[TestResult]:
        """Record test execution outcomes."""
        created_results = []
        for r in results:
            tr = TestResult(
                run_id=run_id,
                test_case_id=r.get("test_case_id"),
                saved_test_id=r.get("saved_test_id"),
                source=r.get("source", "planned"),
                outcome=r.get("outcome", "passed"),
                duration_ms=int(r.get("durationMs", 0)),
                error_message=r.get("errorMessage"),
                worker=r.get("worker", "w1"),
            )
            self.db.add(tr)
            created_results.append(tr)
        self.db.flush()
        return created_results

    def get_results(self, scope: Scope, run_id: str) -> List[TestResult]:
        """Get all test execution results for a run."""
        stmt = (
            select(TestResult)
            .join(Run, TestResult.run_id == Run.id)
            .join(Project, Run.project_id == Project.id)
            .where(TestResult.run_id == run_id)
        )
        if not scope.is_system:
            if not scope.user_id:
                return []
            stmt = stmt.where(Project.owner_id == scope.user_id)
        return list(self.db.scalars(stmt).all())
