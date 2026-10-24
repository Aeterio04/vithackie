"""Run repository managing test execution state, metrics, and application topology."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.db.base import utc_now
from kawach.db.models import AppMap, LlmUsage, Project, Run, RunMetric, RunStageTime
from kawach.repositories.base import BaseRepository, Scope


class RunRepository(BaseRepository):
    """Scoped repository for test runs and lifecycle telemetry."""

    def create_run(
        self,
        scope: Scope,
        run_id: str,
        project_id: str,
        mode: str = "manual",
        trigger_type: str = "manual",
        spec_version: int = 1,
        is_golden: bool = False,
    ) -> Run:
        """Create a new run entity under a project."""
        run = Run(
            id=run_id,
            project_id=project_id,
            created_by=scope.user_id,
            mode=mode,
            stage="created",
            trigger_type=trigger_type,
            spec_version=spec_version,
            is_golden=is_golden,
            progress={"stage": "created", "step": "Initializing run", "done": 0, "total": 10},
        )
        self.db.add(run)
        self.db.flush()
        return run

    def get_run(self, scope: Scope, run_id: str) -> Optional[Run]:
        """Fetch run ensuring user owns the parent project or created the run."""
        from sqlalchemy import or_
        stmt = select(Run).outerjoin(Project, Run.project_id == Project.id).where(Run.id == run_id)
        if not scope.is_system:
            if not scope.user_id:
                return None
            stmt = stmt.where(or_(Project.owner_id == scope.user_id, Run.created_by == scope.user_id))
        return self.db.scalars(stmt).first()

    def list_runs(self, scope: Scope, project_id: Optional[str] = None) -> List[Run]:
        """List runs scoped to user and optionally filtered by project."""
        from sqlalchemy import or_
        stmt = select(Run).outerjoin(Project, Run.project_id == Project.id)
        if not scope.is_system:
            if not scope.user_id:
                return []
            stmt = stmt.where(or_(Project.owner_id == scope.user_id, Run.created_by == scope.user_id))
        if project_id:
            stmt = stmt.where(Run.project_id == project_id)
        stmt = stmt.order_by(Run.created_at.desc())
        return list(self.db.scalars(stmt).all())


    def set_stage(
        self,
        scope: Scope,
        run_id: str,
        stage: str,
        step: str = "",
        done: Optional[int] = None,
        total: Optional[int] = None,
    ) -> Optional[Run]:
        """Update run execution stage and progress indicators."""
        run = self.get_run(scope, run_id)
        if not run:
            return None

        now = utc_now()
        run.stage = stage
        prog = dict(run.progress or {})
        prog["stage"] = stage
        if step:
            prog["step"] = step
        if done is not None:
            prog["done"] = done
        if total is not None:
            prog["total"] = total
        run.progress = prog

        if stage == "exploring" and not run.started_at:
            run.started_at = now
        elif stage in ("done", "failed", "cancelled"):
            run.ended_at = now

        # Record stage timing
        st = RunStageTime(
            run_id=run_id,
            stage=stage,
            started_at=now,
        )
        self.db.add(st)
        self.db.flush()
        return run

    def fail_run(self, scope: Scope, run_id: str, error_message: str) -> Optional[Run]:
        """Transition run to failed stage with error reason."""
        run = self.get_run(scope, run_id)
        if not run:
            return None

        run.stage = "failed"
        run.error = error_message
        run.ended_at = utc_now()
        prog = dict(run.progress or {})
        prog["stage"] = "failed"
        prog["step"] = f"Failed: {error_message}"
        run.progress = prog
        self.db.flush()
        return run

    def save_app_map(
        self,
        scope: Scope,
        run_id: str,
        data: Dict[str, Any],
        pages_visited: int = 0,
        duration_seconds: float = 0.0,
        budget_hit: bool = False,
    ) -> AppMap:
        """Persist explored app topology map for run."""
        run = self.get_run(scope, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found or not owned by user")

        app_map = self.db.get(AppMap, run_id)
        if app_map:
            app_map.data = data
            app_map.pages_visited = pages_visited
            app_map.duration_seconds = duration_seconds
            app_map.budget_hit = budget_hit
        else:
            app_map = AppMap(
                run_id=run_id,
                data=data,
                pages_visited=pages_visited,
                duration_seconds=duration_seconds,
                budget_hit=budget_hit,
            )
            self.db.add(app_map)
        self.db.flush()
        return app_map

    def get_app_map(self, scope: Scope, run_id: str) -> Optional[AppMap]:
        """Retrieve app map for run."""
        run = self.get_run(scope, run_id)
        if not run:
            return None
        return self.db.get(AppMap, run_id)

    def save_metrics(
        self,
        scope: Scope,
        run_id: str,
        data: Dict[str, Any],
        wall_clock_seconds: float = 0.0,
    ) -> RunMetric:
        """Persist compiled metrics snapshot for run."""
        run = self.get_run(scope, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found or not owned by user")

        metric = self.db.get(RunMetric, run_id)
        if metric:
            metric.data = data
            metric.wall_clock_seconds = wall_clock_seconds
        else:
            metric = RunMetric(
                run_id=run_id,
                data=data,
                wall_clock_seconds=wall_clock_seconds,
            )
            self.db.add(metric)
        self.db.flush()
        return metric

    def get_metrics(self, scope: Scope, run_id: str) -> Optional[RunMetric]:
        """Fetch metrics for run."""
        run = self.get_run(scope, run_id)
        if not run:
            return None
        return self.db.get(RunMetric, run_id)

    def record_llm_usage(
        self,
        scope: Scope,
        run_id: str,
        agent: str,
        calls: int = 1,
        cache_hits: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> LlmUsage:
        """Record token consumption and spend for an agent call."""
        record = LlmUsage(
            run_id=run_id,
            agent=agent,
            calls=calls,
            cache_hits=cache_hits,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        self.db.add(record)
        self.db.flush()
        return record
