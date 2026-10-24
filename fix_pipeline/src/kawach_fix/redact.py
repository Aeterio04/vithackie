"""Secret redaction utilities and logging filter for Kawach GitHub Fix Pipeline.

Ensures credentials, API tokens, and PATs are scrubbed from:
- Log messages and tracebacks
- Artifact files (JSON)
- Output FixResult payloads
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
from pydantic import BaseModel

TOKEN_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9_]{30,}", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}", re.IGNORECASE),
    re.compile(r"gsk_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{20,})", re.IGNORECASE),
    re.compile(r"(?:token|password|secret|pat)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{15,})['\"]?", re.IGNORECASE),
]

REDACTED_SUB = "[REDACTED_SECRET]"


def redact_text(text: str, extra_secrets: Optional[Sequence[str]] = None) -> str:
    """Scrub sensitive credential tokens and patterns from a string."""
    if not text:
        return text

    result = text
    # First redact explicit secrets
    if extra_secrets:
        for sec in extra_secrets:
            if sec and len(sec) >= 4:
                result = result.replace(sec, REDACTED_SUB)

    # Redact known token patterns
    for pat in TOKEN_PATTERNS:
        result = pat.sub(REDACTED_SUB, result)

    return result


def redact_data(obj: Any, extra_secrets: Optional[Sequence[str]] = None) -> Any:
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


class RedactingLoggingFilter(logging.Filter):
    """Logging filter that redacts token patterns from log records."""

    def __init__(self, extra_secrets: Optional[Sequence[str]] = None):
        super().__init__()
        self.extra_secrets = list(extra_secrets or [])

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg, self.extra_secrets)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_data(record.args, self.extra_secrets)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(redact_data(a, self.extra_secrets) for a in record.args)
        return True


def write_artifact(
    runs_dir: Path,
    run_id: str,
    filename: str,
    data: Union[BaseModel, Dict[str, Any], List[Any], str],
    extra_secrets: Optional[Sequence[str]] = None,
) -> Path:
    """Save redacted JSON or text artifact under runs_dir/<run_id>/<filename>."""
    target_dir = runs_dir / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    out_file = target_dir / filename

    if isinstance(data, BaseModel):
        payload = redact_data(data.model_dump(), extra_secrets=extra_secrets)
        content = json.dumps(payload, indent=2)
    elif isinstance(data, (dict, list)):
        payload = redact_data(data, extra_secrets=extra_secrets)
        content = json.dumps(payload, indent=2)
    else:
        content = redact_text(str(data), extra_secrets=extra_secrets)

    out_file.write_text(content, encoding="utf-8")
    return out_file
