"""Live visibility: waiting for runs, tailing the SSE stream, logs, events, workers, app map."""

import asyncio
import json
import logging
import time
from urllib.parse import urlparse
from typing import Annotated, Any, AsyncIterator, Optional

from mcp.server.fastmcp import Context
from pydantic import Field

from ..client import get_client
from ..errors import KawachError
from ..formatting import STAGES, STAGE_MEANING, TERMINAL_STAGES, hint, listing, trim
from . import READ, tool
from .bugs import load_bugs
from .catalog import norm_test

log = logging.getLogger("kawach_mcp.observe")

RID = Annotated[str, Field(description="Run id, from list_runs or start_run")]
_sleep = asyncio.sleep       # patched in tests
_now = time.monotonic        # patched in tests


async def _retry(fn, attempts: int = 3):
    """Retry transient failures (backend unreachable / 5xx) with backoff; 404 and 4xx fail fast."""
    for i in range(attempts):
        try:
            return await fn()
        except KawachError as e:
            transient = e.kind in ("unreachable", "timeout") or (e.status_code or 0) >= 500
            if not transient or i == attempts - 1:
                raise
            await _sleep(0.5 * (2 ** i))


async def _notify(ctx: Any, progress: float, total: float, message: str) -> None:
    """Best-effort MCP progress + log message; a client that ignores them must never break the tool."""
    if ctx is None:
        return
    try:
        await ctx.report_progress(progress=progress, total=total, message=message)
        await ctx.info(message)
    except Exception as e:  # noqa: BLE001
        log.debug("progress notification failed: %s", type(e).__name__)


async def _snapshot(run_id: str) -> dict:
    client = get_client()
    run = await _retry(lambda: client.get(f"/runs/{run_id}"))
    stage, step = run.get("stage"), None
    if stage not in TERMINAL_STAGES and stage != "awaiting_review":
        try:
            ex = await client.get(f"/runs/{run_id}/execution")
            step = next((w.get("current_step") for w in ex.get("workers") or []
                         if w.get("status") not in (None, "idle")), None)
        except KawachError as e:
            if e.kind == "unreachable":
                raise
    return {"run": run, "stage": stage, "step": step, "percent": run.get("progress")}


async def _terminal_payload(run_id: str, snap: dict) -> dict:
    client, stage = get_client(), snap["stage"]
    out: dict = {}
    try:
        if stage == "awaiting_review":
            tests = [norm_test(t) for t in await client.get(f"/runs/{run_id}/catalog") or []]
            by: dict = {}
            for t in tests:
                by[t["status"]] = by.get(t["status"], 0) + 1
            out["catalog_counts"] = {"total": len(tests), "by_status": by}
            out["next_step_hint"] = hint("The catalog is ready for review: call get_catalog, then review_tests or approve_all_and_resume.")
        elif stage == "done":
            bugs = await load_bugs(client, run_id)
            c = lambda s: sum(1 for b in bugs if b["status"] == s)  # noqa: E731
            counts = snap["run"].get("counts") or {}
            out["digest"] = {"metrics": {k: counts.get(k) for k in ("total_tests", "passed_tests", "failed_tests")},
                             "bugs": {"confirmed": c("confirmed"), "flaky": c("flaky"), "not_reproduced": c("not_reproduced"), "unverified": c("unverified")}}
            out["next_step_hint"] = hint("Call list_bugs for confirmed defects and get_report for the summary.")
        elif stage in ("failed", "cancelled"):
            logs = await client.get(f"/runs/{run_id}/logs") or []
            errs = [x for x in logs if x.get("level") in ("error", "warn", "warning")] or logs
            out["error"] = trim(" | ".join(f"[{x.get('source')}] {x.get('message')}" for x in errs[-3:]), 600) or "No error text recorded."
            out["next_step_hint"] = hint("Read get_logs for details and consider retry_run." if stage == "failed"
                                         else "The run was cancelled; start_run to try again.")
    except KawachError as e:
        if e.kind == "unreachable":
            raise
        out["detail_error"] = str(e)
    return out


async def wait_core(run_id: str, ctx: Any, until_stages: list, timeout_seconds: int, poll_seconds: int) -> dict:
    """Poll a run until it reaches one of `until_stages` (or a terminal stage) or the timeout passes."""
    bad = [s for s in until_stages if s not in STAGES]
    if bad or not until_stages:
        raise KawachError(f"Invalid until_stages {bad or until_stages}: use stages from {', '.join(STAGES)}.")
    timeout = max(1, min(int(timeout_seconds), 600))
    poll = max(1, min(int(poll_seconds), 10))
    start, last_key = _now(), None
    while True:
        snap = await _snapshot(run_id)
        stage, step, pct = snap["stage"], snap["step"], snap["percent"]
        elapsed = round(_now() - start, 1)
        key = (stage, step, pct)
        if key != last_key:
            last_key = key
            await _notify(ctx, float(pct or 0), 100.0, f"{stage}: {step or STAGE_MEANING.get(stage, '')}")
        base = {"run_id": run_id, "stage": stage, "step": step,
                "progress": {"stage": stage, "percent": pct, "step": step}, "elapsed_seconds": elapsed}
        if stage in until_stages or stage in TERMINAL_STAGES:
            extra = await _terminal_payload(run_id, snap)
            note = {} if stage in until_stages else {"note": f"Run ended in '{stage}' before reaching {until_stages}."}
            return {**base, "still_running": False, **note, **extra}
        remaining = timeout - (_now() - start)
        if remaining <= 0:
            return {**base, "still_running": True,
                    "next_step_hint": hint("Still in progress. Call wait_for_run again.")}
        await _sleep(min(poll, max(remaining, 0.01)))


@tool(READ)
async def wait_for_run(
    run_id: RID,
    ctx: Context,
    until_stages: Annotated[list[str], Field(description="Return when the run reaches any of these stages")] = [
        "awaiting_review", "done", "failed", "cancelled"],
    timeout_seconds: Annotated[int, Field(ge=1, le=600, description="Max seconds to wait (hard max 600)")] = 120,
    poll_seconds: Annotated[int, Field(ge=1, le=10, description="Seconds between polls")] = 3,
) -> dict:
    """Wait (with live progress) until a run reaches a stage you care about, or the timeout passes.

    Use after start_run or a review call instead of polling get_run. Never errors on timeout: it returns
    still_running=true and you simply call it again (clients cap tool-call time). On awaiting_review it
    returns catalog counts; on done a digest of metrics and bug counts; on failed the error text.
    """
    return await wait_core(run_id, ctx, until_stages, timeout_seconds, poll_seconds)


async def _frames(lines: AsyncIterator[str]) -> AsyncIterator[tuple[str, str]]:
    """Parse Server-Sent Events into (event_name, data) frames; multi-line data joined with newlines."""
    event, data = "message", []
    async for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if data:
                yield event, "\n".join(data)
            event, data = "message", []
        elif line.startswith(":"):
            continue
        else:
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                event = value
            elif field == "data":
                data.append(value)
    if data:
        yield event, "\n".join(data)


@tool(READ)
async def tail_run_stream(
    run_id: RID,
    seconds: Annotated[int, Field(ge=1, le=30, description="Max seconds to listen (hard max 30)")] = 10,
    max_events: Annotated[int, Field(ge=1, le=200, description="Max events to collect (hard max 200)")] = 40,
) -> dict:
    """Listen to a run's live event stream for a few seconds and summarize what happened.

    Bounded by time and event count, stops early at run.done, and always closes the connection. The
    backend replays existing log history first, so use a larger max_events to reach live events.
    Returns {logs, stage_changes, tests, budget, workers, run_done, events_seen}.
    """
    seconds = max(1, min(int(seconds), 30))
    max_events = max(1, min(int(max_events), 200))
    out: dict = {"logs": [], "stage_changes": [], "tests": [], "budget": None, "workers": {},
                 "run_done": False, "events_seen": 0}
    stage_val: dict = {}

    async def collect() -> None:
        agen = get_client().stream_lines(f"/runs/{run_id}/stream")
        try:
            async for event, data in _frames(agen):
                try:
                    payload = json.loads(data)
                except ValueError:
                    payload = {"message": data}
                if not isinstance(payload, dict):
                    payload = {"message": str(payload)}
                kind = payload.get("type") or event
                if kind in ("ping", "heartbeat", "keepalive"):
                    continue
                out["events_seen"] += 1
                if kind == "log":
                    out["logs"].append(f"[{payload.get('source', 'log')}] {payload.get('message', '')}")
                elif kind in ("run.status", "stage"):
                    out["stage_changes"].append({"status": payload.get("status"), "progress": payload.get("progress")})
                elif kind in ("test.update", "test.status"):
                    t = payload.get("test") or payload
                    out["tests"].append({"id": t.get("id"), "title": t.get("title"), "status": t.get("status"),
                                         "duration_ms": t.get("duration_ms"), "error": t.get("error_message")})
                elif kind == "budget.update":
                    out["budget"] = payload.get("usage") or payload
                elif kind in ("worker.update", "worker.status"):
                    w = payload.get("worker") or payload
                    out["workers"][w.get("id", "?")] = {"status": w.get("status"), "test": w.get("current_test_id"),
                                                        "step": w.get("current_step")}
                elif kind == "catalog.ready":
                    out["catalog_tests"] = len(payload.get("tests") or [])
                elif kind == "run.done":
                    out["run_done"] = True
                    stage_val["final"] = (payload.get("run") or {}).get("stage")
                    break
                if out["events_seen"] >= max_events:
                    out["event_limit_reached"] = True
                    break
        finally:
            await agen.aclose()

    try:
        await asyncio.wait_for(collect(), timeout=seconds)
    except asyncio.TimeoutError:
        out["time_limit_reached"] = True
    if stage_val.get("final"):
        out["final_stage"] = stage_val["final"]
    out["logs"] = out["logs"][-100:]
    out["tests"] = out["tests"][-60:]
    out["next_step_hint"] = hint("Run finished: call get_run / list_bugs." if out["run_done"]
                                 else "Call tail_run_stream again, or wait_for_run to block until a stage change.")
    return out


@tool(READ)
async def get_logs(
    run_id: RID,
    limit: Annotated[int, Field(ge=1, le=500)] = 50,
    offset: Annotated[int, Field(ge=0, description="With tail=True: newest lines to skip; otherwise lines from the start")] = 0,
    level: Annotated[Optional[str], Field(description="Only this level: info, warn, error, debug")] = None,
    tail: Annotated[bool, Field(description="Show the newest lines (default) instead of the oldest")] = True,
) -> dict:
    """Read the run's pipeline log lines ("[source] message"), newest by default.

    The backend returns the full log (last 500 lines kept), so paging happens here. Returns
    {lines, total, showing}. Use after a failure to see why.
    """
    logs = await get_client().get(f"/runs/{run_id}/logs") or []
    if level:
        logs = [x for x in logs if x.get("level") == level]
    total = len(logs)
    if tail:
        end = max(0, total - offset)
        chosen = logs[max(0, end - limit):end]
    else:
        chosen = logs[offset:offset + limit]
    return {"lines": [f"[{x.get('source')}] {x.get('message')}" for x in chosen], "total": total,
            "showing": len(chosen), "order": "oldest first within the window"}


@tool(READ)
async def get_events(run_id: RID, limit: Annotated[int, Field(ge=1, le=200)] = 50) -> dict:
    """Timeline of milestone events (stage changes, catalog ready, test results, completion, errors)."""
    events = await get_client().get(f"/runs/{run_id}/events") or []
    rows = []
    for ev in events:
        try:
            p = json.loads(ev.get("data") or "{}")
        except ValueError:
            continue
        kind = p.get("type")
        if kind == "run.status":
            rows.append({"id": ev.get("id"), "type": kind, "summary": f"status={p.get('status')} progress={p.get('progress')}"})
        elif kind == "catalog.ready":
            rows.append({"id": ev.get("id"), "type": kind, "summary": f"{len(p.get('tests') or [])} tests proposed"})
        elif kind == "test.update":
            t = p.get("test") or {}
            rows.append({"id": ev.get("id"), "type": kind, "summary": f"{t.get('id')} {t.get('status')}"})
        elif kind == "run.done":
            rows.append({"id": ev.get("id"), "type": kind, "summary": f"stage={(p.get('run') or {}).get('stage')}"})
        elif kind == "log" and p.get("level") in ("error", "warn", "warning"):
            rows.append({"id": ev.get("id"), "type": "log", "summary": trim(f"[{p.get('source')}] {p.get('message')}", 200)})
    return listing("events", rows[-limit:], limit, total_milestones=len(rows))


@tool(READ)
async def get_execution(run_id: RID) -> dict:
    """Snapshot of the workers and test queue right now: who runs what, test statuses, budget used."""
    ex = await get_client().get(f"/runs/{run_id}/execution")
    tests = ex.get("tests") or []
    by: dict = {}
    for t in tests:
        by[t.get("status")] = by.get(t.get("status"), 0) + 1
    usage = ex.get("budget_usage") or {}
    return {
        "workers": [{"id": w.get("id"), "name": w.get("name"), "status": w.get("status"),
                     "current_test": w.get("current_test_id"), "current_step": w.get("current_step"),
                     "screenshot_url": w.get("latest_screenshot_url")} for w in ex.get("workers") or []],
        "tests_by_status": by,
        "active_tests": [{"id": t.get("id"), "title": t.get("title"), "worker": t.get("worker_id")}
                         for t in tests if t.get("status") == "running"],
        "elapsed_minutes": usage.get("elapsed_minutes"), "budget_usage": usage,
    }


@tool(READ)
async def get_app_map(
    run_id: RID,
    detail: Annotated[str, Field(description="summary (first 15 pages) or full (up to 40 pages with actions)")] = "summary",
) -> dict:
    """Show what the explorer learned about the app: pages, forms, features.

    Returns base URL, summary text, features, page count, total forms and the page list. Empty until the
    exploring stage has produced a map.
    """
    if detail not in ("summary", "full"):
        raise KawachError("detail must be 'summary' or 'full'.")
    client = get_client()
    m = await client.get(f"/runs/{run_id}/app-map")
    pages = m.get("pages") or []
    extra: dict = {}
    try:  # richer fields (summary text, features) live only in the raw file
        extra = json.loads(await client.get_text(f"/runs/{run_id}/files/app_map.json"))
    except (KawachError, ValueError) as e:
        if isinstance(e, KawachError) and e.kind == "unreachable":
            raise
    limit = 15 if detail == "summary" else 40
    actions = {n.get("url"): n.get("actions_found") for n in m.get("nodes") or []}
    rows = []
    for p in pages[:limit]:
        row = {"path": urlparse(p["url"]).path or "/",
               "title": trim(p.get("title"), 80), "interactive_elements": p.get("interactive_elements"),
               "forms": p.get("forms_count")}
        if detail == "full":
            row["actions"] = (actions.get(p["url"]) or [])[:8]
            row["status_code"] = p.get("status_code")
        rows.append(row)
    out = {"base_url": m.get("root_url"), "summary": trim(extra.get("summary"), 800) or None,
           "features": [f.get("name") for f in extra.get("features") or []][:20],
           "page_count": m.get("total_pages", len(pages)),
           "total_forms": sum(p.get("forms_count") or 0 for p in pages), "pages": rows}
    if len(pages) > limit:
        out["truncated"] = True
        out["total"] = len(pages)
    if not pages:
        out["message"] = "No app map yet; it is produced during the 'exploring' stage."
    return out
