"""Error type and HTTP status mapping. Messages are written for an AI agent."""

from __future__ import annotations

from typing import Any, Optional

_SECRETS: set[str] = set()


def add_secret(value: Optional[str]) -> None:
    """Register a secret so it is scrubbed from any error text."""
    if value and len(value) >= 3:
        _SECRETS.add(value)


def redact(text: str) -> str:
    for s in _SECRETS:
        text = text.replace(s, "[redacted]")
    return text


class KawachError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, hint: Optional[str] = None,
                 kind: str = "error"):
        super().__init__(redact(message))
        self.status_code = status_code
        self.hint = hint
        self.kind = kind  # "error" | "unreachable" | "timeout" | "auth"


def unreachable(base_url: str, kind: str = "unreachable") -> KawachError:
    return KawachError(
        f"Cannot reach the KAWACH backend at {base_url}. Is it running? (start it, then retry)",
        hint="Start the backend, then retry.", kind=kind,
    )


def _detail_text(body: Any) -> str:
    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, str):
            return d
        if isinstance(d, list):
            return _validation_text(d)
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
    return ""


def _validation_text(items: list) -> str:
    parts = []
    for it in items:
        if isinstance(it, dict):
            loc = ".".join(str(x) for x in it.get("loc", []) if x != "body")
            parts.append(f"{loc}: {it.get('msg', '')}".strip(": "))
        else:
            parts.append(str(it))
    return "; ".join(parts)


def map_status(status: int, body: Any, raw_text: str = "") -> KawachError:
    detail = _detail_text(body)
    if status == 401:
        return KawachError("Authentication failed. Check KAWACH_EMAIL / KAWACH_PASSWORD (or KAWACH_TOKEN).",
                           status, kind="auth")
    if status == 403:
        return KawachError(f"Not allowed to do that. {detail}".strip(), status)
    if status == 404:
        return KawachError("Not found (it may not exist or may belong to another account).", status)
    if status == 409:
        return KawachError(detail or "Conflict with the current state.", status)
    if status == 422:
        fields = _validation_text(body["detail"]) if isinstance(body, dict) and isinstance(body.get("detail"), list) else detail
        return KawachError(f"Invalid input: {fields}".strip(), status)
    if status == 429:
        return KawachError("Rate limited, retry shortly.", status)
    if status >= 500:
        return KawachError(f"Backend error ({status}): {(raw_text or detail)[:300]}", status)
    return KawachError(detail or f"Unexpected response ({status}): {raw_text[:300]}", status)
