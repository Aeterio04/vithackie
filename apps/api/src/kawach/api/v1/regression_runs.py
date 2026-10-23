"""Regression runs trigger endpoint for manual and saved suite execution."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.api.deps import get_db, get_owned_project, require_scope
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.db.models.saved_tests import RunSelectedTest
from kawach.services.idempotency import IdempotencyService
from kawach.services.regression_service import RegressionService

router = APIRouter(prefix="/projects/{project_id}/regression-runs", tags=["regression-runs"])


class RegressionRunTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    test_ids: Optional[List[str]] = None
    commit_sha: Optional[str] = "manual"
    files_changed: Optional[List[str]] = None
    force_full: bool = False
    branch: Optional[str] = "main"
    message: Optional[str] = "Manual regression suite trigger"


class RegressionRunTriggerResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run_id: str
    project_id: str
    commit_sha: str
    status: str
    selected_test_ids: List[str]
    created_at: datetime


@router.post("", response_model=RegressionRunTriggerResponse, status_code=status.HTTP_201_CREATED)
def trigger_regression_run(
    project_id: str,
    payload: Optional[RegressionRunTriggerRequest] = None,
    current_user: User = Depends(require_scope("runs:write")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """Trigger a regression run for saved tests, diff-selected tests, or a specific test subset."""
    payload = payload or RegressionRunTriggerRequest()

    # Check idempotency
    cached = IdempotencyService.check_or_record(
        user_id=current_user.id,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    if cached:
        status_code, response_data = cached
        return JSONResponse(status_code=status_code, content=response_data)

    svc = RegressionService(db)
    run_id, commit_event_id = svc.run_regression(
        project_id=project_id,
        commit_sha=payload.commit_sha or "manual",
        files_changed=payload.files_changed,
        branch=payload.branch or "main",
        message=payload.message or "",
        force_full=payload.force_full,
        explicit_test_ids=payload.test_ids,
    )

    # Fetch recorded selected tests
    selected_tests = db.scalars(
        select(RunSelectedTest.saved_test_id).where(RunSelectedTest.run_id == run_id)
    ).all()

    now = datetime.now(timezone.utc)
    resp_data = RegressionRunTriggerResponse(
        run_id=run_id,
        project_id=project_id,
        commit_sha=payload.commit_sha or "manual",
        status="running",
        selected_test_ids=list(selected_tests),
        created_at=now,
    )
    IdempotencyService.store_response(
        user_id=current_user.id,
        idempotency_key=idempotency_key,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        response_data=resp_data.model_dump(mode="json"),
    )
    return resp_data

