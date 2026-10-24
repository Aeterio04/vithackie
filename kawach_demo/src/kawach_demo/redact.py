"""Redaction helper ensuring no secrets leak to terminal, logs, or argv."""

import re
from typing import Any, Dict, List, Optional, Sequence
from pydantic import BaseModel, SecretStr

TOKEN_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9_]{30,}", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}", re.IGNORECASE),
    re.compile(r"gsk_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z-_]{20,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{20,})", re.IGNORECASE),
]

REDACTED_SUB = "[REDACTED_SECRET]"


def redact_text(text: str, extra_secrets: Optional[Sequence[Any]] = None) -> str:
    """Scrub sensitive credential tokens and patterns from a string."""
    if not text:
        return text

    result = str(text)

    # 1. Redact explicit secrets
    if extra_secrets:
        for sec in extra_secrets:
            if not sec:
                continue
            val = sec.get_secret_value() if isinstance(sec, SecretStr) else str(sec)
            if val and len(val) >= 4:
                result = result.replace(val, REDACTED_SUB)

    # 2. Redact known token patterns
    for pat in TOKEN_PATTERNS:
        result = pat.sub(REDACTED_SUB, result)

    return result


def redact_data(obj: Any, extra_secrets: Optional[Sequence[Any]] = None) -> Any:
    """Recursively scrub strings within dicts, lists, and pydantic models."""
    if isinstance(obj, str):
        return redact_text(obj, extra_secrets=extra_secrets)
    if isinstance(obj, dict):
        return {k: redact_data(v, extra_secrets=extra_secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_data(item, extra_secrets=extra_secrets) for item in obj]
    if isinstance(obj, tuple):
        return tuple(redact_data(item, extra_secrets=extra_secrets) for item in obj)
    if isinstance(obj, BaseModel):
        dumped = obj.model_dump()
        return redact_data(dumped, extra_secrets=extra_secrets)
    return obj
