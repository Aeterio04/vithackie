"""Compact, agent-friendly shaping of backend payloads."""

from __future__ import annotations

from typing import Any, Iterable, Optional

MAX_OUTPUT_CHARS = 20_000
DEFAULT_LIMIT = 50

STAGE_MEANING = {
    "created": "Run accepted and queued; exploration has not started yet.",
    "exploring": "The explorer is crawling the target app and mapping its pages.",
    "planning": "The planner is drafting the test catalog from the app map and spec.",
    "awaiting_review": "Manual mode: the catalog is ready and waiting for human/agent approval before any test runs.",
    "scripting": "Approved tests are being turned into Playwright scripts.",
    "running": "Playwright is executing the tests against the target app.",
    "verifying": "Failures are being replayed (3x) to confirm they are real bugs and not flakes.",
    "reporting": "The final report is being assembled.",
    "done": "Finished. Results, bugs and the report are available.",
    "failed": "The run failed with an error before completing.",
    "cancelled": "The run was cancelled.",
}
STAGES = tuple(STAGE_MEANING)
TERMINAL_STAGES = ("done", "failed", "cancelled")


def trim(text: Any, n: int = 300) -> str:
    s = "" if text is None else str(text)
    if len(s) <= n:
        return s
    return f"{s[:n]}[truncated {len(s) - n} chars]"


def cap_list(items: Iterable[Any], limit: int = DEFAULT_LIMIT) -> tuple[list, bool]:
    items = list(items)
    limit = max(1, int(limit))
    return items[:limit], len(items) > limit


def listing(key: str, rows: list, limit: int = DEFAULT_LIMIT, **extra: Any) -> dict:
    """Standard list envelope: rows capped, with total/truncated markers."""
    shown, truncated = cap_list(rows, limit)
    out: dict = {key: shown, "count": len(shown), **extra}
    if truncated:
        out["truncated"] = True
        out["total"] = len(rows)
    return out


def hint(text: str) -> str:
    return text.strip()


def _first(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return default


def short_run(run: dict) -> dict:
    counts = run.get("counts") or {}
    return {
        "run_id": _first(run, "runId", "id"),
        "project_id": _first(run, "projectId", "project_id"),
        "target_url": _first(run, "targetUrl", "target_url"),
        "stage": run.get("stage"),
        "mode": _first(run, "review_mode", "mode"),
        "created_at": run.get("created_at"),
        "progress_percent": run.get("progress") if isinstance(run.get("progress"), (int, float)) else None,
        "metrics": {k: counts[k] for k in (
            "total_tests", "passed_tests", "failed_tests", "confirmed_bugs", "flaky_bugs", "pending_reviews")
            if k in counts} or None,
    }


def short_project(p: dict) -> dict:
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "target_url": _first(p, "targetUrl", "target_url", "testUrl"),
        "default_mode": _first(p, "defaultMode", "default_mode"),
        "run_count": _first(p, "runCount", "run_count"),
        "saved_test_count": _first(p, "savedTestCount", "saved_test_count", default=0),
        "last_run_status": _first(p, "lastRunStatus", "last_run_status"),
        "github_url": _first(p, "githubUrl", "github_url") or None,
        "has_pat": bool(p.get("hasPat")),
    }


def fmt_verification(attempts: Optional[list]) -> str:
    if not attempts:
        return "not verified"
    ok = sum(1 for a in attempts if (a.get("reproduced") if isinstance(a, dict) else a))
    return f"{ok}/{len(attempts)} reproduced"
