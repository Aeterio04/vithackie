# SCAFFOLD: not implemented (Signature verification is active)
"""Public Webhook ingestion endpoints (GitHub HMAC-SHA256 signature verified)."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from kawach.api.deps import get_db
from kawach.core.config import settings
from kawach.integrations.github.webhook_signature import is_delivery_processed, verify_github_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def receive_github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    x_github_delivery: str = Header(None, alias="X-GitHub-Delivery"),
    db: Session = Depends(get_db),
):
    """Receive and verify GitHub push / pull_request webhook events.

    Verifies HMAC-SHA256 signature using GITHUB_WEBHOOK_SECRET.
    Rejects unauthorized requests with 401 Unauthorized.
    Rejects duplicate delivery IDs with 409 Conflict.
    Returns 501 Not Implemented because the downstream execution loop is scaffolded.
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

    # Cryptographically verified, but execution pipeline is scaffolded
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="GitHub commit regression trigger is scaffolded but not implemented in this phase.",
    )
