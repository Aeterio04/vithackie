"""Idempotency service ensuring safe retries for async use-cases."""

from datetime import datetime, timezone
import hashlib
import json
from threading import Lock
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, status


class IdempotencyRecord:
    """Cached response for an idempotent operation."""

    def __init__(
        self,
        key: str,
        user_id: str,
        payload_hash: str,
        status_code: int,
        response_data: Any,
    ):
        self.key = key
        self.user_id = user_id
        self.payload_hash = payload_hash
        self.status_code = status_code
        self.response_data = response_data
        self.created_at = datetime.now(timezone.utc)


class IdempotencyService:
    """Thread-safe idempotency manager."""

    _records: Dict[str, IdempotencyRecord] = {}
    _lock = Lock()

    @staticmethod
    def compute_payload_hash(payload: Any) -> str:
        """Compute stable SHA-256 hash of request payload."""
        if hasattr(payload, "model_dump"):
            data = payload.model_dump()
        elif hasattr(payload, "dict"):
            data = payload.dict()
        elif isinstance(payload, dict):
            data = payload
        else:
            data = str(payload)

        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def check_or_record(
        cls,
        user_id: str,
        idempotency_key: Optional[str],
        payload: Any,
    ) -> Optional[Tuple[int, Any]]:
        """Check for existing idempotency record.

        - If no key provided: returns None.
        - If matching record exists with identical payload: returns (status_code, response_data).
        - If matching record exists with DIFFERENT payload: raises 409 Conflict.
        - If key does not exist: returns None.
        """
        if not idempotency_key or not idempotency_key.strip():
            return None

        lookup_key = f"{user_id}:{idempotency_key.strip()}"
        payload_hash = cls.compute_payload_hash(payload)

        with cls._lock:
            existing = cls._records.get(lookup_key)
            if existing:
                if existing.payload_hash == payload_hash:
                    return (existing.status_code, existing.response_data)
                else:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key collision with different request payload",
                    )
        return None

    @classmethod
    def store_response(
        cls,
        user_id: str,
        idempotency_key: Optional[str],
        payload: Any,
        status_code: int,
        response_data: Any,
    ) -> None:
        """Store the response for a successfully processed idempotent request."""
        if not idempotency_key or not idempotency_key.strip():
            return

        lookup_key = f"{user_id}:{idempotency_key.strip()}"
        payload_hash = cls.compute_payload_hash(payload)

        with cls._lock:
            cls._records[lookup_key] = IdempotencyRecord(
                key=idempotency_key.strip(),
                user_id=user_id,
                payload_hash=payload_hash,
                status_code=status_code,
                response_data=response_data,
            )

    @classmethod
    def clear(cls) -> None:
        """Reset records (used in tests)."""
        with cls._lock:
            cls._records.clear()
