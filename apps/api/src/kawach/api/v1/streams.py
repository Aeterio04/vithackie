"""Real-time SSE event streaming, log retrieval, and live worker inspection."""

import asyncio
from datetime import datetime, timezone
import json
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from kawach.api.deps import get_owned_run
from kawach.api.v1.mappers.catalog_mapper import transform_test_to_frontend
from kawach.api.v1.mappers.run_mapper import (
    build_execution_state,
    compute_progress_percentage,
    map_stage_to_status,
    transform_run_to_frontend,
)
from kawach.core.clock import now_iso
from kawach.db.models.runs import Run as DbRun
from kawach.schemas import AppMap, Catalog, Results, Run
from kawach.services.run_service import (
    get_run_events,
    get_run_logs,
    record_event,
)
from kawach.storage import artifacts as storage

router = APIRouter(tags=["streams"])


@router.get("/runs/{run_id}/execution")
def get_execution_state(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve live worker states and test execution progress."""
    return build_execution_state(run_id)


@router.get("/runs/{run_id}/tests")
def get_tests(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve list of executed tests with statuses."""
    state = build_execution_state(run_id)
    return state["tests"]


@router.get("/runs/{run_id}/logs")
def get_logs(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Retrieve full chronological pipeline logs for the run."""
    return get_run_logs(run_id)


@router.get("/runs/{run_id}/events")
def poll_run_events(
    run_id: str,
    since: Optional[str] = None,
    _run: DbRun = Depends(get_owned_run),
):
    """Fallback endpoint for polling events when SSE is not supported."""
    events = get_run_events(run_id)
    if since:
        idx = next((i for i, ev in enumerate(events) if ev["id"] == since), -1)
        if idx >= 0:
            return events[idx + 1:]
    return events[-50:]


@router.get("/runs/{run_id}/stream")
async def stream_run_sse(
    run_id: str,
    _run: DbRun = Depends(get_owned_run),
):
    """Server-Sent Events endpoint streaming typed events for useRunStream.ts."""
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        last_stage = None
        last_step = None
        catalog_sent = False
        last_log_idx = 0
        seen_test_status: Dict[str, str] = {}
        last_budget_time = 0.0
        last_screenshot_sent = None

        existing_logs = get_run_logs(run_id)
        for entry in existing_logs:
            log_event = {"type": "log", **entry}
            yield f"data: {json.dumps(log_event)}\n\n"
        last_log_idx = len(existing_logs)

        # Stream until the run reaches a terminal stage (previously capped at 1200 x 0.5 s = 10 min,
        # after which the stream ended WITHOUT a run.done event and the UI stayed on "running").
        idle_ticks = 0
        while True:
            r = storage.load_model(run_id, "run.json", Run)
            if not r:
                break
            idle_ticks += 1
            if idle_ticks % 30 == 0:
                yield ": heartbeat\n\n"

            current_status = map_stage_to_status(r.stage)
            progress_val = compute_progress_percentage(r)
            step_text = r.progress.step if r.progress else ""

            if r.stage != last_stage:
                last_stage = r.stage
                status_event = {
                    "type": "run.status",
                    "status": current_status,
                    "progress": progress_val,
                }
                record_event(run_id, status_event)
                yield f"data: {json.dumps(status_event)}\n\n"

            current_logs = get_run_logs(run_id)
            if len(current_logs) > last_log_idx:
                for entry in current_logs[last_log_idx:]:
                    log_event = {"type": "log", **entry}
                    yield f"data: {json.dumps(log_event)}\n\n"
                last_log_idx = len(current_logs)

            if step_text and step_text != last_step:
                last_step = step_text
                step_log_event = {
                    "type": "log",
                    "timestamp": now_iso(),
                    "level": "info",
                    "source": "pipeline",
                    "message": f"[{r.stage.upper()}] {step_text}",
                }
                record_event(run_id, step_log_event)
                yield f"data: {json.dumps(step_log_event)}\n\n"

            if r.stage in ("awaiting_review", "scripting", "running", "verifying", "reporting", "done") and not catalog_sent:
                cat = storage.load_model(run_id, "catalog.json", Catalog)
                if cat and cat.tests:
                    tests_json = [transform_test_to_frontend(t) for t in cat.tests]
                    catalog_event = {
                        "type": "catalog.ready",
                        "tests": tests_json,
                    }
                    record_event(run_id, catalog_event)
                    yield f"data: {json.dumps(catalog_event)}\n\n"
                    catalog_sent = True

            rdir = storage.run_dir(run_id)
            live_dir = rdir / "live"
            res = storage.load_model(run_id, "results.json", Results)
            cat = storage.load_model(run_id, "catalog.json", Catalog)

            live_data: Dict[str, dict] = {}
            if live_dir.exists():
                for jf in live_dir.glob("*.json"):
                    try:
                        with open(jf, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            tid = data.get("id") or data.get("testId") or jf.stem
                            live_data[tid] = data
                    except Exception:
                        pass

            if cat and cat.tests:
                for t in cat.tests:
                    current_test_status = "queued"
                    duration = None
                    worker_id = "w1"
                    err_msg = None

                    if res and res.tests:
                        match = next((rt for rt in res.tests if rt.testId == t.id), None)
                        if match:
                            current_test_status = "passed" if match.outcome == "passed" else "failed"
                            duration = match.durationMs
                            err_msg = match.errorMessage

                    if current_test_status == "queued" and t.id in live_data:
                        ldata = live_data[t.id]
                        st = ldata.get("status")
                        if st in ("running", "passed", "failed"):
                            current_test_status = st
                        duration = ldata.get("duration_ms")
                        worker_id = ldata.get("worker_id") or "w1"
                        err_msg = ldata.get("error_message")

                    if seen_test_status.get(t.id) != current_test_status:
                        seen_test_status[t.id] = current_test_status
                        test_update_event = {
                            "type": "test.update",
                            "test": {
                                "id": t.id,
                                "run_id": run_id,
                                "catalog_test_id": t.id,
                                "title": t.title,
                                "status": current_test_status,
                                "duration_ms": duration,
                                "worker_id": worker_id,
                                "error_message": err_msg,
                            },
                        }
                        record_event(run_id, test_update_event)
                        yield f"data: {json.dumps(test_update_event)}\n\n"

            latest_screen = None
            if live_dir.exists():
                pngs = sorted(live_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                if pngs:
                    latest_screen = f"/api/v1/runs/{run_id}/files/live/{pngs[0].name}"
            if not latest_screen:
                ev_dir = rdir / "evidence"
                if ev_dir.exists():
                    pngs = sorted(ev_dir.glob("*/screenshot.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if pngs:
                        tid = pngs[0].parent.name
                        latest_screen = f"/api/v1/runs/{run_id}/files/evidence/{tid}/screenshot.png"

            is_active = r.stage in ("running", "scripting", "verifying", "exploring")
            w1_active = None
            w2_active = None
            for tid, ldata in live_data.items():
                if ldata.get("status") == "running":
                    if ldata.get("worker_id") == "w2":
                        w2_active = tid
                    else:
                        w1_active = tid

            w1_screen = f"/api/v1/runs/{run_id}/files/live/w1.png" if (live_dir.exists() and (live_dir / "w1.png").exists()) else latest_screen
            w2_screen = f"/api/v1/runs/{run_id}/files/live/w2.png" if (live_dir.exists() and (live_dir / "w2.png").exists()) else latest_screen

            if (latest_screen and latest_screen != last_screenshot_sent) or (time.time() - last_budget_time > 2.0):
                last_screenshot_sent = latest_screen
                worker1_event = {
                    "type": "worker.update",
                    "worker": {
                        "id": "w1",
                        "kind": "runner",
                        "status": "running" if is_active else ("error" if r.stage == "failed" else "idle"),
                        "current_test_id": w1_active or (list(live_data.keys())[-1] if live_data else None),
                        "current_step": r.progress.step if r.progress else "Executing test suite...",
                        "latest_screenshot_url": w1_screen,
                        "screenshot_updated_at": now_iso(),
                    },
                }
                record_event(run_id, worker1_event)
                yield f"data: {json.dumps(worker1_event)}\n\n"

                worker2_event = {
                    "type": "worker.update",
                    "worker": {
                        "id": "w2",
                        "kind": "runner",
                        "status": "running" if (is_active and (w2_active or r.stage == "running")) else ("error" if r.stage == "failed" else "idle"),
                        "current_test_id": w2_active,
                        "current_step": f"Executing {w2_active}" if w2_active else ("Awaiting task..." if not is_active else "Executing test suite..."),
                        "latest_screenshot_url": w2_screen,
                        "screenshot_updated_at": now_iso(),
                    },
                }
                record_event(run_id, worker2_event)
                yield f"data: {json.dumps(worker2_event)}\n\n"

            now = time.time()
            if now - last_budget_time >= 2.0:
                last_budget_time = now
                elapsed = 0.1
                if r.createdAt:
                    try:
                        c_dt = datetime.fromisoformat(r.createdAt.replace("Z", "+00:00"))
                        now_dt = datetime.now(timezone.utc)
                        elapsed = max(0.1, round((now_dt - c_dt).total_seconds() / 60.0, 1))
                    except Exception:
                        pass
                app_map = storage.load_model(run_id, "app_map.json", AppMap)
                completed_count = sum(1 for st in seen_test_status.values() if st in ("passed", "failed"))
                budget_event = {
                    "type": "budget.update",
                    "usage": {
                        "elapsed_minutes": elapsed,
                        "pages_crawled": len(app_map.pages) if (app_map and app_map.pages) else 0,
                        "steps_executed": completed_count,
                        "active_workers": 2 if is_active else 0,
                    },
                }
                record_event(run_id, budget_event)
                yield f"data: {json.dumps(budget_event)}\n\n"

            if r.stage in storage.TERMINAL_STAGES:
                run_done_event = {
                    "type": "run.done",
                    "run": transform_run_to_frontend(run_id),
                }
                record_event(run_id, run_done_event)
                yield f"data: {json.dumps(run_done_event)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
