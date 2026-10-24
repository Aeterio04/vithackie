"""Run management service for lifecycle, background execution, and logging."""

import json
from datetime import datetime, timezone
from pathlib import Path
import secrets
import shutil
import threading
import time
from typing import Any, Dict, List, Optional

from kawach.core.clock import now_iso
from kawach.core.config import settings
from kawach.core.ids import new_run_id
from kawach.schemas import Budgets, Mode, Run, RunInput, Stage
from kawach.services.spec_parser import parse_spec_raw
from kawach.storage import artifacts as storage
from kawach.storage.secrets import write_secret_password
from kawach.workflows import run_execute, run_explore_plan

from kawach.storage.artifacts import (
    RUN_EVENTS_CACHE,
    RUN_LOGS_CACHE,
    get_run_events,
    get_run_logs,
    log_pipeline,
    record_event,
)


def create_run(
    target_url: str,
    mode: Mode = "manual",
    prompt: str = "",
    spec_raw: str = "",
    username: str = "",
    password: str = "",
    budgets: Optional[Budgets] = None,
    project_id: Optional[str] = None,
) -> Run:
    """Initialize a new test run, persist metadata and inputs, and start explore/plan."""
    run_id = new_run_id()
    created_at = now_iso()
    budgets_obj = budgets or Budgets()

    spec_items = parse_spec_raw(spec_raw)

    run_input = RunInput(
        runId=run_id,
        createdAt=created_at,
        targetUrl=target_url,
        prompt=prompt,
        specRaw=spec_raw,
        spec=spec_items,
        username=username,
        mode=mode,
        budgets=budgets_obj,
    )
    storage.save_model(run_id, "input.json", run_input)

    if password:
        write_secret_password(run_id, password)

    run = Run(
        runId=run_id,
        createdAt=created_at,
        updatedAt=created_at,
        stage="created",
        mode=mode,
        targetUrl=target_url,
        projectId=project_id,
    )
    storage.save_model(run_id, "run.json", run)

    log_pipeline(
        run_id,
        f"Initialized KAWACH test session for {target_url} in {mode} mode.",
        source="system",
    )

    def _bg_explore_plan():
        try:
            run_explore_plan(run_id)
            r = storage.get_run(run_id)
            if r.mode == "autonomous" and r.stage not in ("failed", "cancelled"):
                run_execute(run_id)
        except Exception as e:
            storage.fail_run(run_id, f"Execution error: {e}")

    threading.Thread(target=_bg_explore_plan, daemon=True).start()
    return run


def resume_run(run_id: str) -> Run:
    """Resume execution of an approved test catalog."""
    run = storage.get_run(run_id)
    if run.stage not in ("awaiting_review", "planning", "created"):
        pass

    storage.set_stage(run_id, "scripting", step="Approved test catalog: commencing script generation")
    log_pipeline(run_id, "Catalog review completed. Resuming execution pipeline...", source="user")

    def _bg_execute():
        try:
            run_execute(run_id)
        except Exception as e:
            storage.fail_run(run_id, f"Execution error: {e}")

    threading.Thread(target=_bg_execute, daemon=True).start()
    return storage.get_run(run_id)


def cancel_run(run_id: str) -> Run:
    """Cancel an active run."""
    run = storage.set_stage(run_id, "cancelled", step="Cancelled by user")
    log_pipeline(run_id, "Run was cancelled by user.", level="warn", source="user")
    return run


def delete_run(run_id: str) -> None:
    """Delete run directory and clear memory cache."""
    r_dir = storage.run_dir(run_id)
    if r_dir.exists():
        shutil.rmtree(r_dir, ignore_errors=True)
    RUN_LOGS_CACHE.pop(run_id, None)
    RUN_EVENTS_CACHE.pop(run_id, None)
