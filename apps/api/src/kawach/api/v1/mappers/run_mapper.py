"""Mappers for converting Run and execution models to frontend schemas."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from kawach.core.clock import now_iso
from kawach.core.config import settings
from kawach.schemas import AppMap, BugsFile, Catalog, Results, Run, RunInput
from kawach.storage import artifacts as storage


def map_stage_to_status(stage: str) -> str:
    """Map backend execution stage to frontend RunStatus enum."""
    mapping = {
        "created": "created",
        "exploring": "exploring",
        "planning": "planning",
        "awaiting_review": "awaiting_review",
        "scripting": "executing",
        "running": "executing",
        "verifying": "verifying",
        "reporting": "reporting",
        "done": "completed",
        "failed": "failed",
        "script_generation_failed": "failed",
        "done_with_environment_issue": "completed",
        "cancelled": "cancelled",
    }
    return mapping.get(stage, "created")


def compute_progress_percentage(run: Run) -> int:
    """Calculate integer progress 0-100 based on stage and step progress."""
    stage_weights = {
        "created": (0, 5),
        "exploring": (5, 30),
        "planning": (30, 50),
        "awaiting_review": (50, 50),
        "scripting": (50, 65),
        "running": (65, 80),
        "verifying": (80, 95),
        "reporting": (95, 99),
        "done": (100, 100),
        "failed": (100, 100),
        "cancelled": (100, 100),
    }
    low, high = stage_weights.get(run.stage, (0, 0))
    if run.stage in ("done", "failed", "cancelled", "awaiting_review", "script_generation_failed", "done_with_environment_issue"):
        return high

    if run.progress and run.progress.total and run.progress.total > 0:
        step_ratio = min(1.0, max(0.0, (run.progress.done or 0) / run.progress.total))
        return int(low + (high - low) * step_ratio)

    return low


def build_frontend_counts(run_id: str) -> dict:
    """Compute summary counts for tests, bugs, and reviews from disk."""
    cat = storage.load_model(run_id, "catalog.json", Catalog)
    res = storage.load_model(run_id, "results.json", Results)
    bugs_f = storage.load_model(run_id, "bugs.json", BugsFile)

    total_tests = len(cat.tests) if (cat and cat.tests) else (len(res.tests) if (res and res.tests) else 0)
    passed_tests = 0
    failed_tests = 0
    if res and res.tests:
        for t in res.tests:
            if t.outcome == "passed":
                passed_tests += 1
            elif t.outcome in ("assertion_failure", "test_error"):
                failed_tests += 1

    suspected = 0
    confirmed = 0
    flaky = 0
    not_reproduced = 0
    rdir = storage.run_dir(run_id)
    if bugs_f and bugs_f.bugs:
        from kawach.schemas import Verification
        for b in bugs_f.bugs:
            ver_status = None
            ver_file = rdir / "verification" / f"{b.id}.json"
            if ver_file.exists():
                try:
                    ver = storage.load_model(run_id, f"verification/{b.id}.json", Verification)
                    if ver and hasattr(ver, "status") and ver.status:
                        ver_status = ver.status
                except Exception:
                    pass

            st = ver_status or getattr(b, "status", "")
            if st == "confirmed":
                confirmed += 1
            elif st == "flaky":
                flaky += 1
            elif st == "not_reproduced":
                not_reproduced += 1
            else:
                suspected += 1

    pending_reviews = 0
    if cat and cat.tests:
        pending_reviews = sum(1 for t in cat.tests if getattr(t, "status", "") == "proposed")

    return {
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "failed_tests": failed_tests,
        "suspected_bugs": suspected,
        "confirmed_bugs": confirmed,
        "flaky_bugs": flaky,
        "not_reproduced_bugs": not_reproduced,
        "pending_reviews": pending_reviews,
        # Frontend aliases for ProjectOverviewTab & TestRunsTab
        "tests": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "confirmed": confirmed,
        "suspected": suspected,
        "flaky": flaky,
        "not_reproduced": not_reproduced,
    }


def transform_run_to_frontend(run_id: str) -> dict:
    """Transform backend Run & Input models into frontend RunSchema."""
    run = storage.load_model(run_id, "run.json", Run)
    if not run:
        raise FileNotFoundError(f"Run {run_id} not found")

    run_input = storage.load_model(run_id, "input.json", RunInput)
    prompt = run_input.prompt if run_input else ""
    target_url = run.targetUrl or (run_input.targetUrl if run_input else "http://localhost:4000")

    counts = build_frontend_counts(run_id)
    progress_pct = compute_progress_percentage(run)
    frontend_status = map_stage_to_status(run.stage)

    finished_at = None
    if run.stage in ("done", "failed", "cancelled", "script_generation_failed", "done_with_environment_issue"):
        finished_at = run.updatedAt

    app_map = storage.load_model(run_id, "app_map.json", AppMap)
    pages_crawled = len(app_map.pages) if (app_map and app_map.pages) else 0

    res = storage.load_model(run_id, "results.json", Results)
    steps_executed = len(res.tests) if (res and res.tests) else 0

    elapsed_minutes = 0.1
    if run.createdAt:
        try:
            created_dt = datetime.fromisoformat(run.createdAt.replace("Z", "+00:00"))
            end_dt = datetime.now(timezone.utc)
            if run.stage in ("done", "failed", "cancelled", "script_generation_failed", "done_with_environment_issue") and hasattr(run, "updatedAt") and run.updatedAt:
                try:
                    end_dt = datetime.fromisoformat(run.updatedAt.replace("Z", "+00:00"))
                except Exception:
                    pass
            elapsed_minutes = max(0.1, round((end_dt - created_dt).total_seconds() / 60.0, 1))
        except Exception:
            elapsed_minutes = 0.5

    duration_sec = None
    if res and hasattr(res, "durationSeconds") and res.durationSeconds is not None:
        duration_sec = res.durationSeconds
    elif elapsed_minutes:
        duration_sec = round(elapsed_minutes * 60, 1)

    is_active = run.stage in ("running", "scripting", "verifying", "exploring")

    return {
        "id": run.runId,
        "runId": run.runId,
        "projectId": getattr(run, "projectId", None),
        "project_id": getattr(run, "projectId", None),
        "target_url": target_url,
        "targetUrl": target_url,
        "prompt": prompt,
        "review_mode": run.mode or "manual",
        "status": frontend_status,
        "stage": run.stage,
        "progress": progress_pct,
        "created_at": run.createdAt,
        "finished_at": finished_at,
        "duration_seconds": duration_sec,
        "budgets": {
            "max_pages": run_input.budgets.maxPages if (run_input and run_input.budgets) else settings.MAX_PAGES,
            "max_steps_per_test": 30,
            "max_run_minutes": 15,
            "parallel_workers": 2,
        },
        "budget_usage": {
            "pages_crawled": pages_crawled,
            "steps_executed": steps_executed,
            "elapsed_minutes": elapsed_minutes,
            "active_workers": 2 if is_active else 0,
        },
        "counts": counts,
    }


def build_execution_state(run_id: str) -> dict:
    """Build live execution state with active workers and test queue status."""
    run = storage.load_model(run_id, "run.json", Run)
    res = storage.load_model(run_id, "results.json", Results)
    cat = storage.load_model(run_id, "catalog.json", Catalog)
    app_map = storage.load_model(run_id, "app_map.json", AppMap)

    rdir = storage.run_dir(run_id)
    live_dir = rdir / "live"
    live_data: Dict[str, dict] = {}
    if live_dir.exists():
        for f in live_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
                    tid = data.get("id") or data.get("testId") or f.stem
                    live_data[tid] = data
            except Exception:
                pass

    latest_screenshot_url = None
    screenshot_ts = None
    if live_dir.exists():
        pngs = sorted(live_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        if pngs:
            latest_screenshot_url = f"/api/v1/runs/{run_id}/files/live/{pngs[0].name}"
            screenshot_ts = datetime.fromtimestamp(pngs[0].stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not latest_screenshot_url:
        ev_dir = rdir / "evidence"
        if ev_dir.exists():
            pngs = sorted(ev_dir.glob("*/screenshot.png"), key=lambda p: p.stat().st_mtime, reverse=True)
            if pngs:
                tid = pngs[0].parent.name
                latest_screenshot_url = f"/api/v1/runs/{run_id}/files/evidence/{tid}/screenshot.png"
                screenshot_ts = datetime.fromtimestamp(pngs[0].stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    running_stage = run.stage if run else "created"
    is_active = running_stage in ("running", "scripting", "verifying", "exploring")

    current_step_text = "Awaiting task..."
    if running_stage == "exploring":
        current_step_text = "Crawling pages and analyzing DOM elements"
    elif running_stage == "planning":
        current_step_text = "Synthesizing test catalog and spec mapping"
    elif running_stage == "scripting":
        current_step_text = run.progress.step if (run and run.progress) else "Synthesizing Playwright test scripts"
    elif running_stage == "running":
        current_step_text = run.progress.step if (run and run.progress) else "Executing tests in Playwright sandbox"
    elif running_stage == "verifying":
        current_step_text = run.progress.step if (run and run.progress) else "Deterministic 3x defect verification"
    elif running_stage == "done":
        current_step_text = "All tests completed"

    w1_active_test = None
    w2_active_test = None
    w1_step_text = current_step_text
    w2_step_text = "Awaiting task..." if not is_active else current_step_text

    for tid, ldata in live_data.items():
        w_id = ldata.get("worker_id", "w1")
        st = ldata.get("status")
        if st == "running":
            if w_id == "w2":
                w2_active_test = tid
                w2_step_text = f"Running {tid}: {ldata.get('title', '')}"
            else:
                w1_active_test = tid
                w1_step_text = f"Running {tid}: {ldata.get('title', '')}"

    if not w1_active_test:
        for tid in reversed(list(live_data.keys())):
            if live_data[tid].get("worker_id", "w1") == "w1":
                w1_active_test = tid
                break
    if not w2_active_test:
        for tid in reversed(list(live_data.keys())):
            if live_data[tid].get("worker_id") == "w2":
                w2_active_test = tid
                break

    w1_status = "running" if (is_active and (w1_active_test or running_stage in ("scripting", "exploring"))) else ("error" if running_stage == "failed" else "idle")
    w2_status = "running" if (is_active and (w2_active_test or running_stage == "running")) else ("error" if running_stage == "failed" else "idle")

    w1_screenshot = latest_screenshot_url
    w1_ts = screenshot_ts
    if live_dir.exists() and (live_dir / "w1.png").exists():
        w1_screenshot = f"/api/v1/runs/{run_id}/files/live/w1.png"
        w1_ts = datetime.fromtimestamp((live_dir / "w1.png").stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    w2_screenshot = latest_screenshot_url
    w2_ts = screenshot_ts
    if live_dir.exists() and (live_dir / "w2.png").exists():
        w2_screenshot = f"/api/v1/runs/{run_id}/files/live/w2.png"
        w2_ts = datetime.fromtimestamp((live_dir / "w2.png").stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    workers = [
        {
            "id": "w1",
            "name": "Playwright Worker 1",
            "kind": "exploratory" if running_stage == "exploring" else "runner",
            "status": w1_status,
            "current_test_id": w1_active_test,
            "current_step": w1_step_text,
            "latest_screenshot_url": w1_screenshot,
            "screenshot_updated_at": w1_ts,
        },
        {
            "id": "w2",
            "name": "Playwright Worker 2",
            "kind": "runner",
            "status": w2_status,
            "current_test_id": w2_active_test,
            "current_step": w2_step_text,
            "latest_screenshot_url": w2_screenshot,
            "screenshot_updated_at": w2_ts,
        },
    ]

    tests_list = []
    completed_count = 0
    seen_ids = set()

    def _map_test_outcome(out: Optional[str]) -> str:
        if not out:
            return "queued"
        o = str(out).lower()
        if o in ("passed", "passed_with_issues"):
            return "passed"
        if o == "environment_error":
            return "error"
        if o in ("not_run", "skipped"):
            return "skipped"
        if o == "running":
            return "running"
        if o in ("failed", "assertion_failure", "test_error", "script_error", "setup_error"):
            return "failed"
        return "failed"

    if cat and cat.tests:
        for t in cat.tests:
            outcome = "queued"
            duration = None
            worker_id = "w1"
            err_msg = None

            if res and res.tests:
                match = next((rt for rt in res.tests if rt.testId == t.id or rt.testId.lower() == t.id.lower()), None)
                if match:
                    outcome = _map_test_outcome(match.outcome)
                    duration = match.durationMs
                    err_msg = match.errorMessage

            if t.id in live_data:
                ldata = live_data[t.id]
                worker_id = ldata.get("worker_id") or worker_id
                if outcome == "queued":
                    st = ldata.get("status")
                    outcome = _map_test_outcome(st)
                    duration = ldata.get("duration_ms")
                    err_msg = ldata.get("error_message")

            if outcome in ("passed", "failed", "error"):
                completed_count += 1

            seen_ids.add(t.id)
            tests_list.append({
                "id": t.id,
                "test_id": t.id,
                "run_id": run_id,
                "title": t.title,
                "status": outcome,
                "duration_ms": duration,
                "error_message": err_msg,
                "worker_id": worker_id,
            })

    # Also incorporate tests from results.json (in case catalog.json is missing or had fewer tests)
    if res and res.tests:
        for rt in res.tests:
            if rt.testId not in seen_ids:
                seen_ids.add(rt.testId)
                outcome = _map_test_outcome(rt.outcome)
                worker_id = "w1"
                if rt.testId in live_data:
                    ldata = live_data[rt.testId]
                    worker_id = ldata.get("worker_id") or worker_id

                if outcome in ("passed", "failed", "error"):
                    completed_count += 1

                tests_list.append({
                    "id": rt.testId,
                    "test_id": rt.testId,
                    "run_id": run_id,
                    "title": rt.title or f"Test {rt.testId}",
                    "status": outcome,
                    "duration_ms": rt.durationMs,
                    "error_message": rt.errorMessage,
                    "worker_id": worker_id,
                })

    # Also incorporate live_data if tests are actively running and not yet recorded
    for tid, ldata in live_data.items():
        if tid not in seen_ids:
            seen_ids.add(tid)
            st = ldata.get("status", "running")
            outcome = _map_test_outcome(st)
            tests_list.append({
                "id": tid,
                "test_id": tid,
                "run_id": run_id,
                "title": ldata.get("title") or f"Test {tid}",
                "status": outcome,
                "duration_ms": ldata.get("duration_ms"),
                "error_message": ldata.get("error_message"),
                "worker_id": ldata.get("worker_id", "w1"),
            })

    elapsed_minutes = 0.1
    if run and run.createdAt:
        try:
            created_dt = datetime.fromisoformat(run.createdAt.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            if run.stage in ("done", "failed", "cancelled", "script_generation_failed", "done_with_environment_issue") and hasattr(run, "updatedAt") and run.updatedAt:
                try:
                    now_dt = datetime.fromisoformat(run.updatedAt.replace("Z", "+00:00"))
                except Exception:
                    pass
            elapsed_minutes = max(0.1, round((now_dt - created_dt).total_seconds() / 60.0, 1))
        except Exception:
            elapsed_minutes = 0.5

    pages_crawled = len(app_map.pages) if (app_map and app_map.pages) else 0

    return {
        "workers": workers,
        "tests": tests_list,
        "budget_usage": {
            "pages_crawled": pages_crawled,
            "steps_executed": completed_count,
            "elapsed_minutes": elapsed_minutes,
            "active_workers": 2 if is_active else 0,
        },
    }
