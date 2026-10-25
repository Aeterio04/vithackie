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

    from kawach.services.spec_structured import has_test_case_blocks
    spec_driven = has_test_case_blocks(spec_raw)
    if spec_driven:
        from kawach.services.spec_budgets import suggest_budgets
        budgets_obj = suggest_budgets(spec_raw, budgets_obj, requested=budgets)

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
        priorityTier="P0" if spec_driven else None,  # first run on a new spec: P0 only
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
            if r.mode == "autonomous" and r.stage not in ("failed", "cancelled", "done_with_environment_issue"):
                run_execute(run_id)
        except Exception as e:
            storage.fail_run(run_id, f"Execution error: {e}")

    threading.Thread(target=_bg_explore_plan, daemon=True).start()
    return run


class SpecAlignmentError(ValueError):
    """Raised when a spec-driven catalog does not match its spec."""


def compute_alignment(run_id: str) -> Optional[dict]:
    """Live alignment of the current catalog vs the structured spec (None if not spec-driven)."""
    from kawach.schemas import Catalog
    from kawach.schemas.spec import StructuredSpec
    from kawach.services.spec_driven import alignment

    raw = storage.read_json(run_id, "spec_structured.json")
    if raw is None:
        return None
    spec = StructuredSpec.model_validate(raw)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    report = alignment(spec, catalog)
    lint_fail = {t.id: t.lint["issues"] for t in (catalog.tests if catalog else []) if t.lint and not t.lint["ok"]}
    report["lintFailures"] = lint_fail
    if lint_fail and report["canStartExecution"]:
        report["canStartExecution"] = False
        report["blockReason"] = f"{len(lint_fail)} test(s) failed the quality lint"
    return report


def resume_run(run_id: str, retry: bool = False, tier: Optional[str] = None) -> Run:
    """Start execution of an approved catalog.

    Idempotent and state-checked: a start/resume request that arrives while the run is still
    exploring/planning (the UI calls /start right after creating the run), is already executing,
    or is finished does nothing, unless `retry` is set for a finished run.
    """
    report = compute_alignment(run_id)
    if report is not None and not report["canStartExecution"]:
        raise SpecAlignmentError(report["blockReason"])
    run = storage.get_run(run_id)
    if tier is not None:
        from kawach.services.spec_driven import VALID_TIERS
        if tier not in VALID_TIERS:
            raise ValueError(f"unknown priority tier {tier!r}; use one of {VALID_TIERS}")
        ri = storage.load_model(run_id, "input.json", RunInput)
        if ri:
            ri.priorityTier = tier
            storage.save_model(run_id, "input.json", ri)
    if run.stage in ("created", "exploring", "planning"):
        log_pipeline(run_id, f"Start request ignored: run is still '{run.stage}'; execution begins after the catalog is reviewed.", level="warn", source="user")
        return run
    if run.stage in ("scripting", "running", "verifying", "reporting"):
        log_pipeline(run_id, f"Start request ignored: run is already '{run.stage}'.", level="warn", source="user")
        return run
    if run.stage in storage.TERMINAL_STAGES:
        if not retry:
            log_pipeline(run_id, f"Start request ignored: run already finished ({run.stage}). Use retry to re-run.", level="warn", source="user")
            return run
        storage.reopen_run(run_id)

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
