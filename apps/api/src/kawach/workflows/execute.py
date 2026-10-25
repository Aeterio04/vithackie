"""LangGraph workflow for Graph 2: Execute, Triage, Verify, and Report."""

import threading
import traceback
from typing import Any, Dict, TypedDict

from langgraph.graph import END, StateGraph

from kawach.core.clock import now_iso
from kawach.core.config import settings
from kawach.schemas import BugsFile, Catalog, Results
from kawach.storage import artifacts as storage
from kawach.workflows import stubs


class ExecuteState(TypedDict):
    runId: str


def _safe_wrapper(node_name: str, fn):
    def wrapper(state: ExecuteState) -> ExecuteState:
        run_id = state.get("runId", "")
        try:
            run = storage.get_run(run_id)
            if run.stage in storage.TERMINAL_STAGES:
                return state
            fn(run_id)
            return state
        except KeyboardInterrupt:
            raise
        except Exception as e:
            err_log = storage.run_dir(run_id) / "error.log"
            with open(err_log, "a", encoding="utf-8") as f:
                f.write(f"\n--- {node_name} failed at {now_iso()} ---\n")
                f.write(traceback.format_exc())
            storage.fail_run(run_id, f"{node_name} failed: {e}")
            return state

    return wrapper


def _log(run_id: str, message: str, level: str = "info"):
    try:
        from kawach.storage.artifacts import log_pipeline
        log_pipeline(run_id, message, level=level, source="pipeline")
    except Exception:
        pass


def node_write_scripts(run_id: str) -> None:
    _log(run_id, "Pipeline: Beginning script synthesis phase for approved test catalog...")
    from kawach.services.spec_driven import is_spec_driven
    if is_spec_driven(run_id):
        from kawach.services.spec_scripts import write_spec_scripts
        write_spec_scripts(run_id)
        _log(run_id, "Pipeline: spec-driven scripts generated deterministically (one per spec TC).")
        return
    if settings.STUB_MODE:
        stubs.stub_write_scripts(run_id)
    else:
        from kawach.agents.script_writer import write_scripts
        write_scripts(run_id)


def _verify_scripts_or_fail(run_id: str) -> bool:
    """Approved tests > 0 but executable scripts == 0 is a failure, never a success."""
    cat = storage.load_model(run_id, "catalog.json", Catalog)
    approved = [t for t in (cat.tests if cat else []) if t.status == "approved"]
    from kawach.schemas import RunInput
    from kawach.services.spec_driven import selected_test_ids
    ri = storage.load_model(run_id, "input.json", RunInput)
    sel = set(selected_test_ids(cat, ri.priorityTier if ri else None))
    approved = [t for t in approved if t.id in sel]
    ok = [t for t in approved if t.scriptStatus == "ok" and t.script]
    if approved and not ok:
        reasons = "; ".join(f"{t.id}: {(t.scriptError or 'no script produced')[:120]}" for t in approved[:50])
        storage.fail_run(
            run_id,
            f"Script generation failed for all {len(approved)} approved tests. {reasons}",
            stage="script_generation_failed",
        )
        _log(run_id, f"Pipeline: SCRIPT GENERATION FAILED - 0 of {len(approved)} approved tests have an executable script. {reasons}", level="error")
        return False
    if not approved:
        storage.fail_run(run_id, "No approved tests to execute.", stage="script_generation_failed")
        _log(run_id, "Pipeline: no approved tests to execute; run marked failed.", level="error")
        return False
    if len(ok) < len(approved):
        bad = [t for t in approved if t not in ok]
        _log(run_id, f"Pipeline: WARNING {len(bad)} of {len(approved)} approved tests have no script: " + ", ".join(t.id for t in bad), level="warn")
    return True


def node_run_tests(run_id: str) -> None:
    if not _verify_scripts_or_fail(run_id):
        return
    storage.set_stage(run_id, "running", step="Executing Playwright test suite")
    _log(run_id, "Pipeline: Executing test suite in Playwright Chromium sandboxes...")
    from kawach.services.spec_driven import is_spec_driven
    if is_spec_driven(run_id):
        from kawach.execution.spec_runner import run_selected
        run_selected(run_id, mode="official")
        return
    if settings.STUB_MODE:
        stubs.stub_run_tests(run_id)
    else:
        from kawach.execution.runner import run_tests
        from kawach.execution.triage import triage
        run_tests(run_id, workers=2)
        triage(run_id)


def node_report_bugs(run_id: str) -> None:
    storage.set_stage(run_id, "verifying", step="Writing bug reports")
    _log(run_id, "Pipeline: Writing defect reports from assertion failures...")
    from kawach.services.spec_driven import is_spec_driven
    if is_spec_driven(run_id):
        return  # findings are produced per TC by the spec-driven harness
    if settings.STUB_MODE:
        stubs.stub_report_bugs(run_id)
    else:
        bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
        if bugs_file and bugs_file.bugs:
            from kawach.agents.bug_reporter import write_bug_reports
            write_bug_reports(run_id)


def node_verify(run_id: str) -> None:
    storage.set_stage(run_id, "verifying", step="Replaying bugs")
    _log(run_id, "Pipeline: Starting deterministic 3x defect verification replays...")
    from kawach.services.spec_driven import is_spec_driven
    if is_spec_driven(run_id):
        return  # site-defect replays are executed by the calibration tooling
    if settings.STUB_MODE:
        stubs.stub_verify(run_id)
    else:
        from kawach.execution.verifier import verify_all
        verifier = verify_all
        verifier(run_id)


def node_build_report(run_id: str) -> None:
    res = storage.load_model(run_id, "results.json", Results)
    cat = storage.load_model(run_id, "catalog.json", Catalog)
    from kawach.schemas import RunInput
    from kawach.services.spec_driven import selected_test_ids
    ri = storage.load_model(run_id, "input.json", RunInput)
    n_approved = len(selected_test_ids(cat, ri.priorityTier if ri else None))
    n_executed = len([t for t in (res.tests if res else []) if t.outcome != "not_run"])
    if n_approved and n_executed == 0:
        storage.fail_run(run_id, f"0 of {n_approved} approved tests were executed; refusing to report success.")
        _log(run_id, f"Pipeline: EXECUTION FAILED - 0 of {n_approved} approved tests were executed.", level="error")
        return
    storage.set_stage(run_id, "reporting", step="Compiling final report and metrics")
    _log(run_id, "Pipeline: Compiling final test coverage metrics and QA executive report...")
    from kawach.services.spec_driven import is_spec_driven
    if is_spec_driven(run_id):
        from kawach.execution.spec_report import build_spec_report
        build_spec_report(run_id, ["official"])
    elif settings.STUB_MODE:
        stubs.stub_build_report(run_id)
    else:
        from kawach.execution.reporting import build_metrics, build_report
        build_metrics(run_id)
        build_report(run_id)

    current_run = storage.get_run(run_id)
    if current_run.stage != "done_with_environment_issue":
        storage.set_stage(run_id, "done", step="Run completed successfully")
    _log(run_id, "Pipeline: QA execution workflow finished successfully.")

    try:
        from kawach.db.session import SessionLocal
        from kawach.db.models.runs import Run as DbRun
        from kawach.services.saved_test_service import SavedTestService
        from kawach.db.base import utc_now

        with SessionLocal() as db:
            db_run = db.query(DbRun).filter(DbRun.id == run_id).first()
            if db_run and db_run.project_id:
                svc = SavedTestService(db)
                svc.sync_run_tests(db_run.project_id, run_id, user_id=db_run.created_by)
                db_run.stage = "done"
                db_run.ended_at = utc_now()
                db.commit()
    except Exception as e:
        _log(run_id, f"Notice: Could not auto-sync tests to project catalog: {e}", level="warning")


def should_continue(state: ExecuteState) -> str:
    run_id = state.get("runId", "")
    try:
        run = storage.get_run(run_id)
        if run.stage in storage.TERMINAL_STAGES:
            return "failed"
    except Exception:
        return "failed"
    return "ok"


def build_execute_graph():
    """Build and compile Graph 2 (Scripts -> Run -> Bug Reports -> Verify -> Report)."""
    builder = StateGraph(ExecuteState)

    builder.add_node("write_scripts", _safe_wrapper("write_scripts", node_write_scripts))
    builder.add_node("run_tests", _safe_wrapper("run_tests", node_run_tests))
    builder.add_node("report_bugs", _safe_wrapper("report_bugs", node_report_bugs))
    builder.add_node("verify", _safe_wrapper("verify", node_verify))
    builder.add_node("build_report", _safe_wrapper("build_report", node_build_report))

    builder.set_entry_point("write_scripts")

    builder.add_conditional_edges(
        "write_scripts",
        should_continue,
        {"ok": "run_tests", "failed": END},
    )
    builder.add_conditional_edges(
        "run_tests",
        should_continue,
        {"ok": "report_bugs", "failed": END},
    )
    builder.add_conditional_edges(
        "report_bugs",
        should_continue,
        {"ok": "verify", "failed": END},
    )
    builder.add_conditional_edges(
        "verify",
        should_continue,
        {"ok": "build_report", "failed": END},
    )
    builder.add_edge("build_report", END)

    return builder.compile()


_graph2 = None


_EXEC_ACTIVE: set = set()
_EXEC_GUARD = threading.Lock()


def run_execute(run_id: str) -> None:
    """Run Graph 2 exactly once per run at a time, and only after exploration/planning/review finished."""
    global _graph2
    run = storage.get_run(run_id)
    if run.stage in ("created", "exploring", "planning"):
        _log(run_id, f"Pipeline: execute request ignored - run is still '{run.stage}' (plan/review not finished).", level="warn")
        return
    with _EXEC_GUARD:
        if run_id in _EXEC_ACTIVE:
            _log(run_id, "Pipeline: duplicate execute request ignored - execution already in progress.", level="warn")
            return
        _EXEC_ACTIVE.add(run_id)
    try:
        # Gate must have passed BEFORE any script generation/dispatch; run it now if it never did.
        if storage.read_json(run_id, "gate_result.json") is None:
            from kawach.execution.circuit_breaker import run_gate_check
            from kawach.schemas import RunInput
            ri = storage.load_model(run_id, "input.json", RunInput)
            if run_gate_check(run_id, ri.targetUrl if ri else ""):
                return
        _log(run_id, "Pipeline: circuit-breaker gate verified before dispatch.")
        if _graph2 is None:
            _graph2 = build_execute_graph()
        _graph2.invoke({"runId": run_id})
    finally:
        with _EXEC_GUARD:
            _EXEC_ACTIVE.discard(run_id)
