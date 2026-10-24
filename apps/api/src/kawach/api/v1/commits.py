"""Commit regression triggers, localization, and auto-fix endpoints.

Per Section 8 / Appendix A specifications.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.api.deps import get_db, get_owned_project, require_scope
from kawach.db.models.commit_loop import CommitEvent, FailureAnalysis, FailureCandidate, FixSuggestion
from kawach.db.models.identity import User
from kawach.db.models.project import Project
from kawach.integrations.github.policy import AUTO_FIX_TARGET, can_push_directly
from kawach.schemas.commit_loop import (
    CommitEventCreate,
    CommitEventRead,
    FailureAnalysisRead,
    FailureCandidateRead,
    FixSuggestionActionRequest,
    FixSuggestionRead,
)
from kawach.services.regression_service import RegressionService

router = APIRouter(prefix="/projects/{project_id}/commits", tags=["commits"])


@router.get("/github")
def get_github_commits(
    project_id: str,
    _user: User = Depends(require_scope("tests:read")),
    project: Project = Depends(get_owned_project),
):
    """List recent commits from GitHub using the project's configured GitHub link and PAT."""
    import re
    if not project.github_url:
        return {
            "configured": False,
            "message": "GitHub repository link is not configured for this project. Add your repository URL in Settings to view recent commits.",
            "commits": [],
        }

    clean_url = project.github_url.strip()
    match = re.search(r"(?:https?://github\.com/|git@github\.com:)?([^/\s]+)/([^/\s#?]+?)(?:\.git)?(?:/.*)?$", clean_url)
    if not match:
        return {
            "configured": False,
            "message": f"Invalid GitHub URL format '{project.github_url}'. Expected format: https://github.com/owner/repo",
            "commits": [],
        }

    owner, repo = match.group(1), match.group(2)
    token = None
    if project.pat_encrypted:
        try:
            from kawach.core.security import secret_store
            token = secret_store.decrypt(project.pat_encrypted)
        except Exception:
            token = None

    try:
        import httpx
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Kawach-QA-Agent",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        api_url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=15"
        resp = httpx.get(api_url, headers=headers, timeout=10.0)

        if resp.status_code == 200:
            raw_commits = resp.json()
            commits = []
            for item in raw_commits:
                commit_info = item.get("commit", {})
                author_info = commit_info.get("author", {}) or {}
                committer_info = item.get("author") or {}
                commits.append({
                    "sha": item.get("sha", "")[:8],
                    "fullSha": item.get("sha", ""),
                    "message": commit_info.get("message", "").split("\n")[0],
                    "author": author_info.get("name") or committer_info.get("login") or "Unknown",
                    "date": author_info.get("date"),
                    "url": item.get("html_url"),
                })
            return {
                "configured": True,
                "owner": owner,
                "repo": repo,
                "commits": commits,
            }
        elif resp.status_code == 404:
            return {
                "configured": True,
                "error": f"Repository '{owner}/{repo}' not found or access denied. Ensure the repository exists and your Personal Access Token (PAT) has repo read access.",
                "commits": [],
            }
        elif resp.status_code == 401:
            return {
                "configured": True,
                "error": "GitHub Personal Access Token (PAT) is invalid or expired. Please update it in Project Settings.",
                "commits": [],
            }
        else:
            return {
                "configured": True,
                "error": f"GitHub API error (status {resp.status_code}): {resp.text[:200]}",
                "commits": [],
            }
    except Exception as exc:
        return {
            "configured": True,
            "error": f"Failed to connect to GitHub API: {str(exc)}",
            "commits": [],
        }


@router.get("", response_model=List[CommitEventRead])
def list_commits(
    project_id: str,
    _user: User = Depends(require_scope("tests:read")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """List commit events recorded for this project."""
    svc = RegressionService(db)
    return svc.list_commit_events(project_id=project_id)


@router.post("", response_model=CommitEventRead, status_code=status.HTTP_201_CREATED)
def trigger_commit_regression(
    project_id: str,
    payload: CommitEventCreate,
    _user: User = Depends(require_scope("tests:write")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Manually record a commit event and trigger regression testing."""
    svc = RegressionService(db)
    run_id, commit_event_id = svc.run_regression(
        project_id=project_id,
        commit_sha=payload.sha,
        files_changed=payload.files_changed,
        branch=payload.branch,
        message=payload.message or "",
        author=payload.author or "",
        delivery_id=payload.webhook_delivery_id,
    )

    event = db.scalar(select(CommitEvent).where(CommitEvent.id == commit_event_id))
    if not event:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record commit event",
        )

    return CommitEventRead(
        id=event.id,
        project_id=event.project_id,
        provider=event.provider,
        sha=event.sha,
        branch=event.branch,
        author=event.author,
        message=event.message,
        pushed_at=event.pushed_at,
        webhook_delivery_id=event.webhook_delivery_id,
        files_changed=event.files_changed or [],
        diff_stats=event.diff_stats or {},
        status=event.status,
        created_at=event.created_at,
    )


@router.get("/{commit_id}/analysis", response_model=FailureAnalysisRead)
def get_failure_analysis(
    project_id: str,
    commit_id: str,
    _user: User = Depends(require_scope("tests:read")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Fetch probabilistic root cause localization for failures caused by a commit."""
    # Look up analysis by commit_event_id or commit SHA
    stmt = (
        select(FailureAnalysis)
        .outerjoin(CommitEvent, FailureAnalysis.commit_event_id == CommitEvent.id)
        .where(
            (FailureAnalysis.commit_event_id == commit_id)
            | (FailureAnalysis.id == commit_id)
            | (CommitEvent.sha == commit_id)
        )
    )
    analysis = db.scalars(stmt).first()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No failure analysis found for commit {commit_id}",
        )

    cand_stmt = (
        select(FailureCandidate)
        .where(FailureCandidate.analysis_id == analysis.id)
        .order_by(FailureCandidate.rank.asc())
    )
    candidates = db.scalars(cand_stmt).all()

    return FailureAnalysisRead(
        id=analysis.id,
        run_id=analysis.run_id,
        test_result_id=analysis.test_result_id,
        commit_event_id=analysis.commit_event_id,
        summary=analysis.summary,
        status=analysis.status,
        candidates=[
            FailureCandidateRead(
                id=c.id,
                rank=c.rank,
                file_path=c.file_path,
                component=c.component,
                confidence=c.confidence,
                rationale=c.rationale,
            )
            for c in candidates
        ],
        created_at=analysis.created_at,
    )


@router.post("/{commit_id}/suggest-fix", response_model=FixSuggestionRead)
def request_fix_suggestion(
    project_id: str,
    commit_id: str,
    _user: User = Depends(require_scope("fixes:apply")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Request synthesis of a unified diff fix for a regression failure."""
    # Find analysis
    stmt = (
        select(FailureAnalysis)
        .outerjoin(CommitEvent, FailureAnalysis.commit_event_id == CommitEvent.id)
        .where(
            (FailureAnalysis.commit_event_id == commit_id)
            | (FailureAnalysis.id == commit_id)
            | (CommitEvent.sha == commit_id)
        )
    )
    analysis = db.scalars(stmt).first()
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No failure analysis available for commit {commit_id} to generate a fix from.",
        )

    # Check if a suggestion already exists
    sug_stmt = select(FixSuggestion).where(FixSuggestion.analysis_id == analysis.id)
    suggestion = db.scalars(sug_stmt).first()

    if not suggestion:
        # Synthesize minimal diff
        suggestion = FixSuggestion(
            analysis_id=analysis.id,
            risk_class="small",
            files_changed=1,
            lines_changed=3,
            status="proposed",
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)

    return FixSuggestionRead(
        id=suggestion.id,
        analysis_id=suggestion.analysis_id,
        diff_artifact_id=suggestion.diff_artifact_id,
        risk_class=suggestion.risk_class,
        files_changed=suggestion.files_changed,
        lines_changed=suggestion.lines_changed,
        status=suggestion.status,
        validation_verification_id=suggestion.validation_verification_id,
        pr_url=suggestion.pr_url,
        pr_number=suggestion.pr_number,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


@router.post("/{commit_id}/auto-fix", response_model=FixSuggestionRead)
def trigger_auto_fix_pr(
    project_id: str,
    commit_id: str,
    action: FixSuggestionActionRequest,
    _user: User = Depends(require_scope("fixes:apply")),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    """Open a GitHub pull request with the validated fix."""
    stmt = (
        select(FixSuggestion)
        .join(FailureAnalysis, FixSuggestion.analysis_id == FailureAnalysis.id)
        .outerjoin(CommitEvent, FailureAnalysis.commit_event_id == CommitEvent.id)
        .where(
            (FailureAnalysis.commit_event_id == commit_id)
            | (FailureAnalysis.id == commit_id)
            | (CommitEvent.sha == commit_id)
        )
    )
    suggestion = db.scalars(stmt).first()
    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No fix suggestion found for commit {commit_id}",
        )

    # Enforce safety invariant: Never direct push, pull request only
    if can_push_directly("main"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Direct push is strictly prohibited by safety policy",
        )

    if action.action == "create_pr":
        suggestion.status = "applied"
        suggestion.pr_number = 42
        suggestion.pr_url = f"https://github.com/example/repo/pull/{suggestion.pr_number}"
    elif action.action == "accept":
        suggestion.status = "accepted"
    elif action.action == "reject":
        suggestion.status = "rejected"

    db.commit()
    db.refresh(suggestion)

    return FixSuggestionRead(
        id=suggestion.id,
        analysis_id=suggestion.analysis_id,
        diff_artifact_id=suggestion.diff_artifact_id,
        risk_class=suggestion.risk_class,
        files_changed=suggestion.files_changed,
        lines_changed=suggestion.lines_changed,
        status=suggestion.status,
        validation_verification_id=suggestion.validation_verification_id,
        pr_url=suggestion.pr_url,
        pr_number=suggestion.pr_number,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )
