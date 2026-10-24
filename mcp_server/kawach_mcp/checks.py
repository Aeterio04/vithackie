"""Shared validation and pre-flight helpers used by several tool modules."""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from .client import KawachClient
from .errors import KawachError

MODES = ("manual", "autonomous")

# budget key -> (limits-min key, limits-max key) as exposed by /config/defaults
_LIMITED = {
    "max_pages": ("min_pages", "max_pages"),
    "max_steps_per_test": ("min_steps", "max_steps"),
    "max_run_minutes": ("min_minutes", "max_minutes"),
    "parallel_workers": ("min_workers", "max_workers"),
}
# accepted by POST /runs but not covered by the published limits: must just be positive ints
_FREE_POSITIVE = ("explore_seconds", "max_tests", "test_timeout_ms")


def validate_mode(mode: Optional[str], field: str = "review_mode") -> str:
    if mode not in MODES:
        raise KawachError(f"Invalid {field} {mode!r}: must be one of {', '.join(MODES)}.")
    return mode


def validate_url_shape(url: Optional[str], field: str = "target_url") -> str:
    url = (url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise KawachError(f"Invalid {field}: must be a full http:// or https:// URL, got {url!r}.")
    return url


async def validate_budgets(client: KawachClient, budgets: Optional[dict]) -> Optional[dict]:
    if budgets is None:
        return None
    if not isinstance(budgets, dict) or not budgets:
        raise KawachError("budgets must be a non-empty object, e.g. {\"max_pages\": 10}.")
    limits = (await client.get_defaults()).get("limits", {})
    for key, val in budgets.items():
        if isinstance(val, bool) or not isinstance(val, int):
            raise KawachError(f"Invalid budget {key}: expected a whole number, got {val!r}.")
        if key in _LIMITED:
            lo_k, hi_k = _LIMITED[key]
            lo, hi = limits.get(lo_k, 1), limits.get(hi_k)
            if val < lo or (hi is not None and val > hi):
                raise KawachError(f"Invalid budget {key}={val}: must be between {lo} and {hi}.")
        elif key in _FREE_POSITIVE:
            if val <= 0:
                raise KawachError(f"Invalid budget {key}={val}: must be positive.")
        else:
            allowed = ", ".join(list(_LIMITED) + list(_FREE_POSITIVE))
            raise KawachError(f"Unknown budget key {key!r}. Allowed: {allowed}.")
    return budgets


def verdict_for(result: dict) -> str:
    if result.get("allowed") is False:
        if result.get("reachable") is False:
            return "Invalid target URL"
        return "Blocked by SSRF policy"
    if result.get("reachable") is False:
        return "Unreachable, is the app running?"
    return "OK to test"


async def run_target_check(client: KawachClient, target_url: str) -> dict:
    """POST /targets/check and normalise the answer with a plain-language verdict."""
    url = validate_url_shape(target_url)
    raw = await client.post("/targets/check", {"target_url": url})
    out = {
        "allowed": bool(raw.get("allowed")),
        "reachable": bool(raw.get("reachable")),
        "host": urlparse(url).hostname,
        "status_code": raw.get("status_code"),
        "reason": raw.get("reason"),
    }
    out["verdict"] = verdict_for(out)
    return out


def require_nonempty(value: Optional[str], field: str) -> str:
    if value is None or not str(value).strip():
        raise KawachError(f"{field} must not be empty.")
    return str(value).strip()


def project_body(*, name: Any = None, target_url: Any = None, description: Any = None,
                 default_mode: Any = None, budgets: Any = None, github_url: Any = None) -> dict:
    """Map snake_case tool arguments to the backend's camelCase project body (None = omit)."""
    body = {
        "name": name, "targetUrl": target_url, "description": description,
        "defaultMode": default_mode, "budgets": budgets, "githubUrl": github_url,
    }
    return {k: v for k, v in body.items() if v is not None}
