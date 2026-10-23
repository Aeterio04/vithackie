"""Public Webhook ingestion endpoints (GitHub HMAC-SHA256 signature verified)."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.api.deps import get_db
from kawach.core.config import settings
from kawach.db.models.project import Project
from kawach.integrations.github.webhook_signature import is_delivery_processed, verify_github_signature
from kawach.repositories.audit_repo import AuditRepository
from kawach.services.regression_service import RegressionService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def receive_github_webhook(
    request: Request,
    project_id: Optional[str] = Query(None, description="Optional target project ID"),
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    x_github_delivery: str = Header(None, alias="X-GitHub-Delivery"),
    x_github_event: str = Header("push", alias="X-GitHub-Event"),
    db: Session = Depends(get_db),
):
    """Receive and verify GitHub push / pull_request webhook events.

    Verifies HMAC-SHA256 signature using GITHUB_WEBHOOK_SECRET.
    Rejects unauthorized requests with 401 Unauthorized.
    Rejects duplicate delivery IDs with 409 Conflict.
    Triggers commit regression suite and returns 202 Accepted.
    """
    raw_body = await request.body()
    webhook_secret = settings.GITHUB_WEBHOOK_SECRET or "dev-webhook-secret"

    if not x_hub_signature_256:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-Hub-Signature-256 header",
        )

    if not verify_github_signature(raw_body, webhook_secret, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC-SHA256 signature",
        )

    if x_github_delivery and is_delivery_processed(x_github_delivery, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate webhook delivery ID: {x_github_delivery}",
        )

    # Parse JSON payload
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        )

    AuditRepository(db).record(
        action="webhook_receive",
        entity_type="integration",
        metadata={"delivery_id": x_github_delivery, "provider": "github", "event": x_github_event},
        client_type="github",
    )

    # Resolve target project
    target_project_id = project_id
    if not target_project_id:
        repo_info = payload.get("repository", {})
        repo_name = repo_info.get("name")
        if repo_name:
            p = db.scalar(select(Project).where(Project.name == repo_name))
            if p:
                target_project_id = p.id

    if not target_project_id:
        # Default to first available project
        first_proj = db.scalar(select(Project).limit(1))
        if first_proj:
            target_project_id = first_proj.id
        else:
            # Create a default project if none exists
            default_proj = Project(name="default-repo", target_url="http://localhost:4000")
            db.add(default_proj)
            db.commit()
            db.refresh(default_proj)
            target_project_id = default_proj.id

    # Extract commit metadata
    head_commit = payload.get("head_commit") or {}
    sha = payload.get("after") or head_commit.get("id") or "HEAD"
    branch_ref = payload.get("ref", "refs/heads/main")
    branch = branch_ref.replace("refs/heads/", "") if "refs/heads/" in branch_ref else branch_ref
    message = head_commit.get("message", "")
    pusher = payload.get("pusher", {})
    author = pusher.get("name") or (head_commit.get("author") or {}).get("name") or ""

    files_changed_set = set()
    for c in payload.get("commits", []):
        files_changed_set.update(c.get("added", []))
        files_changed_set.update(c.get("modified", []))
        files_changed_set.update(c.get("removed", []))
    if not files_changed_set and head_commit:
        files_changed_set.update(head_commit.get("added", []))
        files_changed_set.update(head_commit.get("modified", []))
        files_changed_set.update(head_commit.get("removed", []))

    files_changed = sorted(list(files_changed_set))

    # Trigger regression
    svc = RegressionService(db)
    run_id, commit_event_id = svc.run_regression(
        project_id=target_project_id,
        commit_sha=sha,
        files_changed=files_changed,
        branch=branch,
        message=message,
        author=author,
        delivery_id=x_github_delivery,
    )

    return {
        "ok": True,
        "event": x_github_event,
        "sha": sha,
        "branch": branch,
        "project_id": target_project_id,
        "run_id": run_id,
        "commit_event_id": commit_event_id,
        "files_changed_count": len(files_changed),
    }
