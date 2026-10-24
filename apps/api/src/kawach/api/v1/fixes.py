"""API endpoints for autonomous GitHub fix pipeline integration."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from kawach.api.deps import get_owned_run, get_user_scope
from kawach.db.models.runs import Run as DbRun
from kawach.db.session import get_db
from kawach.repositories.base import Scope
from kawach.services.fix_service import fix_service

router = APIRouter(tags=["fixes"])


from pydantic import BaseModel, Field, ConfigDict, AliasChoices


class ConfigureGithubPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    github_url: str = Field(..., validation_alias=AliasChoices("github_url", "githubUrl"), description="GitHub repository owner/repo or HTTPS URL.")
    pat: str = Field(..., validation_alias=AliasChoices("pat", "github_pat", "githubPat"), description="Fine-grained or classic GitHub Personal Access Token.")


class CreateFixPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(..., validation_alias=AliasChoices("run_id", "runId"), description="ID of the completed test run.")
    bug_id: Optional[str] = Field(None, validation_alias=AliasChoices("bug_id", "bugId"), description="Optional specific defect ID to fix.")
    repo: Optional[str] = Field(None, description="Optional override for GitHub repository.")
    github_pat: Optional[str] = Field(None, validation_alias=AliasChoices("github_pat", "githubPat", "pat"), description="Optional override for GitHub PAT.")
    target_url: Optional[str] = Field(None, validation_alias=AliasChoices("target_url", "targetUrl"), description="Optional override for target app URL.")
    dry_run: bool = Field(False, validation_alias=AliasChoices("dry_run", "dryRun"), description="When true, computes fix and PR payload but skips write operations.")


@router.get("/runs/{run_id}/fix-readiness")
def get_fix_readiness_endpoint(
    run_id: str,
    db: Session = Depends(get_db),
    _run: DbRun = Depends(get_owned_run),
):
    """Check if parent project has GitHub repository and PAT token configured."""
    return fix_service.get_fix_readiness(run_id=run_id, db=db)


@router.post("/runs/{run_id}/fix-config")
def save_fix_config_endpoint(
    run_id: str,
    payload: ConfigureGithubPayload,
    db: Session = Depends(get_db),
    _run: DbRun = Depends(get_owned_run),
):
    """Save GitHub repository and Personal Access Token for the run's project."""
    try:
        return fix_service.save_github_config(
            run_id=run_id,
            github_url=payload.github_url,
            pat=payload.pat,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/fixes", status_code=status.HTTP_201_CREATED)
def create_fix_endpoint(
    payload: CreateFixPayload,
    db: Session = Depends(get_db),
    scope: Scope = Depends(get_user_scope),
):
    """Launch autonomous GitHub fix pipeline for a detected bug."""
    try:
        return fix_service.start_fix_pipeline(
            run_id=payload.run_id,
            bug_id=payload.bug_id,
            repo=payload.repo,
            github_pat=payload.github_pat,
            target_url=payload.target_url,
            dry_run=payload.dry_run,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to start fix pipeline: {str(e)}")


@router.get("/fixes/{fix_id}")
def get_fix_status_endpoint(
    fix_id: str,
):
    """Retrieve real-time progress, telemetry, and artifacts of an active or completed fix."""
    session = fix_service.get_fix_status(fix_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Fix session {fix_id} not found.")
    return session
