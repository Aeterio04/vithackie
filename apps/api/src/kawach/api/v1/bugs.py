"""Defect reporting and verification endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from kawach.api.deps import get_owned_run, get_user_scope
from kawach.api.v1.mappers.bug_mapper import build_bugs_frontend, transform_bug_to_frontend
from kawach.db.models.bugs import Bug as DbBug
from kawach.db.models.project import Project as DbProject
from kawach.db.models.runs import Run as DbRun
from kawach.db.session import get_db
from kawach.repositories.base import Scope
from kawach.repositories.bug_repo import BugRepository
from kawach.services.bug_service import get_bug, get_bugs, retest_bug
from kawach.storage import artifacts as storage

router = APIRouter(tags=["bugs"])


@router.get("/runs/{run_id}/bugs")
def get_run_bugs(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve defect reports with reproduction outcomes and evidence links. Returns 404 if run not owned."""
    return build_bugs_frontend(run_id)


@router.get("/bugs/{bug_id}")
def get_single_bug(
    bug_id: str,
    scope: Scope = Depends(get_user_scope),
    db: Session = Depends(get_db),
):
    """Find a specific defect report across all runs, respecting tenant ownership."""
    from kawach.repositories.run_repo import RunRepository
    run_repo = RunRepository(db)

    # Check database first
    db_bug = db.get(DbBug, bug_id)
    if db_bug:
        if not scope.is_system and not run_repo.get_run(scope, db_bug.run_id):
            raise HTTPException(status_code=404, detail="Bug not found")
        return transform_bug_to_frontend(db_bug.run_id, get_bug(db_bug.run_id, db_bug.key))

    for r in storage.list_runs():
        if not scope.is_system and not run_repo.get_run(scope, r.runId):
            continue
        b = get_bug(r.runId, bug_id)
        if b:
            return transform_bug_to_frontend(r.runId, b)
    raise HTTPException(status_code=404, detail=f"Bug {bug_id} not found")


@router.post("/runs/{run_id}/bugs/{bug_id}/retest")
def retest_bug_endpoint(
    run_id: str,
    bug_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Execute deterministic 3x replay for candidate bug."""
    try:
        ver = retest_bug(run_id, bug_id)
        b = get_bug(run_id, bug_id)
        return transform_bug_to_frontend(run_id, b)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
