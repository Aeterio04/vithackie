"""Two-step confirmation protocol engine for MCP mutating write tools."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from kawach_mcp.context import get_current_caller


def _canonical_hash(payload: Dict[str, Any], caller_token_hash: Optional[str] = None) -> str:
    """Compute deterministic SHA-256 hash of payload bound to caller identity."""
    filtered = {k: v for k, v in payload.items() if k != "confirmation_id"}
    serialized = json.dumps(filtered, sort_keys=True, separators=(",", ":"), default=str)
    caller_prefix = f"{caller_token_hash}:" if caller_token_hash else ""
    return hashlib.sha256(f"{caller_prefix}{serialized}".encode("utf-8")).hexdigest()


class ConfirmationPreviewResponse(BaseModel):
    """Preview returned in step 1 of mutating tool execution."""
    requires_confirmation: bool = Field(default=True, description="Always true for mutating preview")
    confirmation_id: str = Field(description="Short-lived confirmation token required for step 2 execution")
    expires_in_seconds: int = Field(default=300, description="Time-to-live in seconds before token expires (5m)")
    preview: Dict[str, Any] = Field(description="Detailed impact preview (files touched, policies checked, expected effects)")
    instructions: str = Field(
        default="To execute this action, invoke this tool again with the exact same arguments and include confirmation_id.",
        description="Guidance for the calling LLM or human developer",
    )


class ConfirmationManager:
    """In-memory store for payload-bound, caller-isolated, single-use confirmation tokens."""

    def __init__(self, default_ttl_seconds: float = 300.0, max_entries: int = 1000):
        self.default_ttl = default_ttl_seconds
        self.max_entries = max_entries
        # confirmation_id -> (payload_hash, expires_at)
        self._tokens: Dict[str, Tuple[str, float]] = {}

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [cid for cid, (_, exp) in self._tokens.items() if exp < now]
        for cid in expired:
            self._tokens.pop(cid, None)

    def create_confirmation(
        self,
        payload: Dict[str, Any],
        preview: Dict[str, Any],
        ttl_seconds: Optional[float] = None,
        caller_token_hash: Optional[str] = None,
    ) -> ConfirmationPreviewResponse:
        """Create a new single-use confirmation ID cryptographically bound to caller and payload."""
        self._cleanup_expired()
        if len(self._tokens) >= self.max_entries:
            # Evict oldest entry if full
            oldest_id = min(self._tokens, key=lambda k: self._tokens[k][1])
            self._tokens.pop(oldest_id, None)

        if caller_token_hash is None:
            caller = get_current_caller()
            if caller:
                caller_token_hash = caller.token_hash

        ttl = ttl_seconds or self.default_ttl
        conf_id = f"conf_{uuid.uuid4().hex[:12]}"
        payload_hash = _canonical_hash(payload, caller_token_hash=caller_token_hash)
        expires_at = time.time() + ttl

        self._tokens[conf_id] = (payload_hash, expires_at)
        return ConfirmationPreviewResponse(
            confirmation_id=conf_id,
            expires_in_seconds=int(ttl),
            preview=preview,
        )

    def validate_and_consume(
        self,
        confirmation_id: str,
        payload: Dict[str, Any],
        caller_token_hash: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validate confirmation token existence, expiry, and payload integrity; consume on success."""
        self._cleanup_expired()
        entry = self._tokens.get(confirmation_id)
        if not entry:
            return False, "Confirmation ID not found, already consumed, or invalid."

        stored_hash, expires_at = entry
        if time.time() > expires_at:
            self._tokens.pop(confirmation_id, None)
            return False, "Confirmation ID has expired. Please re-run the tool without confirmation_id to get a fresh preview."

        if caller_token_hash is None:
            caller = get_current_caller()
            if caller:
                caller_token_hash = caller.token_hash

        current_hash = _canonical_hash(payload, caller_token_hash=caller_token_hash)
        if current_hash != stored_hash:
            return False, "Payload mismatch: Action arguments were modified after confirmation was issued."

        # Consume token so it cannot be replayed
        self._tokens.pop(confirmation_id, None)
        return True, None


confirmation_manager = ConfirmationManager()

