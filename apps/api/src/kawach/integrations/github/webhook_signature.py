# Security-critical helper for GitHub Webhook HMAC-SHA256 verification.
"""HMAC-SHA256 signature verification and delivery idempotency for GitHub webhooks."""

import hashlib
import hmac
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from kawach.core.security import constant_time_compare


def compute_github_signature(payload: bytes, secret: str) -> str:
    """Compute GitHub-compatible HMAC-SHA256 hex digest prefixed with 'sha256='."""
    mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def verify_github_signature(
    payload: bytes,
    secret: str,
    signature_header: Optional[str],
) -> bool:
    """Verify incoming X-Hub-Signature-256 header against computed HMAC-SHA256.

    Returns:
        bool: True if signature is cryptographically valid, False otherwise.
    """
    if not secret or not signature_header:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    expected_sig = compute_github_signature(payload, secret)
    return constant_time_compare(signature_header, expected_sig)


def is_delivery_processed(delivery_id: str, db: Session) -> bool:
    """Check if a webhook delivery ID has already been recorded (idempotency check)."""
    if not delivery_id:
        return False
    from kawach.db.models.commit_loop import CommitEvent

    stmt = select(CommitEvent.id).where(CommitEvent.webhook_delivery_id == delivery_id).limit(1)
    result = db.scalar(stmt)
    return result is not None
