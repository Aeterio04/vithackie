"""Regression testing orchestration service.

Handles diff-aware test selection, commit triggers, and regression pipeline execution.
"""

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.core.config import settings
from kawach.db.models.commit_loop import CommitEvent, FailureAnalysis, FixSuggestion
from kawach.db.models.project import Project
from kawach.db.models.runs import Run as DbRun
from kawach.db.models.saved_tests import RunSelectedTest, SavedTest, SavedTestCoverage
from kawach.schemas.commit_loop import CommitEventCreate, CommitEventRead
from kawach.storage import artifacts as storage
from kawach.workflows.regression import RegressionState, regression_graph

logger = logging.getLogger("kawach.services.regression")


class RegressionService:
    """Service orchestrating commit regression testing and diff-aware test selection."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def save_test(
        self,
        project_id: str,
        run_id: str,
        test_id: str,
        name: Optional[str] = None,
    ) -> Any:
        """Compatibility method for legacy protocol."""
        if self.db is None:
            raise NotImplementedError("Saving tests to regression library is scaffolded for future product releases.")
        from kawach.services.saved_test_service import SavedTestService
        from kawach.schemas.saved_tests import SavedTestCreate
        return SavedTestService(self.db).save_test(
            project_id=project_id,
            payload=SavedTestCreate(run_id=run_id, test_id=test_id, name=name),
        )

    def run_regression_suite(
        self,
        project_id: str,
        test_ids: List[str],
        commit_sha: Optional[str] = None,
    ) -> str:
        """Compatibility method for legacy protocol."""
        if self.db is None:
            raise NotImplementedError("Running regression suites is scaffolded for future product releases.")
        run_id, _ = self.run_regression(project_id=project_id, commit_sha=commit_sha or "HEAD", files_changed=[])
        return run_id

    def select_tests_for_diff(
        self,
        project_id: str,
        files_changed: List[str],
        force_full: bool = False,
    ) -> List[str]:
        """Identify saved tests whose coverage touchpoints intersect with modified files.
        
        Matches paths, routes, and component names.
        If no matches or force_full is True, selects all active saved tests.
        """
        if self.db is None:
            raise NotImplementedError("Diff-aware test selection is scaffolded for future product releases.")

        # Fetch active saved tests with their coverage
        stmt = (
            select(SavedTest)
            .where(SavedTest.project_id == project_id, SavedTest.is_active == True)
        )
        saved_tests = self.db.scalars(stmt).all()

        if not saved_tests:
            return []

        all_test_ids = [t.id for t in saved_tests]

        if force_full or not files_changed:
            return all_test_ids

        # Normalize changed file references
        normalized_files = set()
        for f in files_changed:
            norm = f.replace("\\", "/").lower().lstrip("/")
            normalized_files.add(norm)
            # Add basename / stem for fuzzy component match
            stem = Path(norm).stem
            if stem:
                normalized_files.add(stem)

        affected_ids: List[str] = []

        # Check coverage touchpoints for each test
        for test in saved_tests:
            cov_stmt = select(SavedTestCoverage).where(SavedTestCoverage.saved_test_id == test.id)
            coverages = self.db.scalars(cov_stmt).all()

            is_match = False
            for cov in coverages:
                ref_norm = cov.ref.replace("\\", "/").lower().lstrip("/")
                ref_stem = Path(ref_norm).stem

                # Direct match, subpath match, or stem match
                if ref_norm in normalized_files or ref_stem in normalized_files:
                    is_match = True
                    break
                for ch_file in normalized_files:
                    if ch_file.endswith(ref_norm) or ref_norm.endswith(ch_file):
                        is_match = True
                        break

            if is_match and test.id not in affected_ids:
                affected_ids.append(test.id)

        # Fallback: if no touchpoint matched, select all tests to prevent silent regressions
        return affected_ids if affected_ids else all_test_ids

    def record_commit_event(
        self,
        project_id: str,
        payload: CommitEventCreate,
    ) -> CommitEvent:
        """Record or retrieve an ingested Git commit event."""
        # Check idempotency via delivery ID
        existing = self.db.scalar(
            select(CommitEvent).where(
                CommitEvent.webhook_delivery_id == payload.webhook_delivery_id
            )
        )
        if existing:
            return existing

        commit_event = CommitEvent(
            project_id=project_id,
            provider="github",
            sha=payload.sha,
            branch=payload.branch,
            author=payload.author,
            message=payload.message,
            pushed_at=payload.pushed_at,
            webhook_delivery_id=payload.webhook_delivery_id,
            files_changed=payload.files_changed,
            diff_stats=payload.diff_stats,
            status="pending",
        )
        self.db.add(commit_event)
        self.db.commit()
        self.db.refresh(commit_event)
        return commit_event

    def run_regression(
        self,
        project_id: str,
        commit_sha: str = "manual",
        files_changed: Optional[List[str]] = None,
        branch: str = "main",
        message: str = "",
        author: str = "",
        delivery_id: Optional[str] = None,
        force_full: bool = False,
        explicit_test_ids: Optional[List[str]] = None,
    ) -> Tuple[str, str]:
        """Trigger and execute the commit regression loop.
        
        Returns (run_id, commit_event_id).
        """
        # 1. Record CommitEvent
        delivery_id = delivery_id or f"commit_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        resolved_files = files_changed or []
        commit_payload = CommitEventCreate(
            sha=commit_sha,
            branch=branch,
            author=author,
            message=message,
            pushed_at=now,
            webhook_delivery_id=delivery_id,
            files_changed=resolved_files,
            diff_stats={},
        )
        commit_event = self.record_commit_event(project_id, commit_payload)

        # 2. Select tests: explicit list, diff-aware, or full suite
        if explicit_test_ids is not None:
            selected_test_ids = list(explicit_test_ids)
        else:
            selected_test_ids = self.select_tests_for_diff(
                project_id=project_id,
                files_changed=resolved_files,
                force_full=force_full,
            )

        # 3. Create Run record
        run_id = f"reg_{commit_sha[:8]}_{uuid.uuid4().hex[:6]}"
        db_run = DbRun(
            id=run_id,
            project_id=project_id,
            trigger_type="commit",
            commit_event_id=commit_event.id,
            stage="running",
            created_at=now,
        )
        self.db.add(db_run)

        # Record selected tests in link table
        for tid in selected_test_ids:
            self.db.add(
                RunSelectedTest(
                    run_id=run_id,
                    saved_test_id=tid,
                    reason="affected" if tid in selected_test_ids else "full",
                )
            )

        commit_event.status = "running"
        self.db.commit()

        # Initialize storage directory for the run
        storage.run_dir(run_id)
        from kawach.schemas import RunInput, Run as SchemaRun
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        storage.save_model(
            run_id,
            "input.json",
            RunInput(
                runId=run_id,
                createdAt=now_str,
                targetUrl="http://localhost:4000",
                mode="autonomous",
                specRaw=f"Commit Regression for {commit_sha}",
                spec=[],
            ),
        )
        storage.save_model(
            run_id,
            "run.json",
            SchemaRun(
                runId=run_id,
                createdAt=now_str,
                updatedAt=now_str,
                stage="running",
                mode="autonomous",
                targetUrl="http://localhost:4000",
            ),
        )

        # 4. Invoke LangGraph regression state machine
        initial_state: RegressionState = {
            "project_id": project_id,
            "commit_sha": commit_sha,
            "files_changed": files_changed,
            "selected_test_ids": selected_test_ids,
            "failed_test_ids": [],
            "verified_defect_ids": [],
            "analysis_id": None,
            "fix_suggestion_id": None,
            "is_validated": False,
            "status": "started",
            "error": None,
        }

        try:
            final_state = regression_graph.invoke(initial_state)
            commit_event.status = "completed" if not final_state.get("error") else "failed"
            db_run.stage = "completed" if not final_state.get("error") else "failed"
        except Exception as exc:
            logger.error(f"Regression workflow failed for commit {commit_sha}: {exc}")
            commit_event.status = "failed"
            db_run.stage = "failed"

        self.db.commit()
        return run_id, commit_event.id

    def list_commit_events(self, project_id: str) -> List[CommitEventRead]:
        """List all recorded commit events for a project ordered by pushed_at desc."""
        stmt = (
            select(CommitEvent)
            .where(CommitEvent.project_id == project_id)
            .order_by(CommitEvent.pushed_at.desc())
        )
        events = self.db.scalars(stmt).all()
        return [
            CommitEventRead(
                id=e.id,
                project_id=e.project_id,
                provider=e.provider,
                sha=e.sha,
                branch=e.branch,
                author=e.author,
                message=e.message,
                pushed_at=e.pushed_at,
                webhook_delivery_id=e.webhook_delivery_id,
                files_changed=e.files_changed or [],
                diff_stats=e.diff_stats or {},
                status=e.status,
                created_at=e.created_at,
            )
            for e in events
        ]
