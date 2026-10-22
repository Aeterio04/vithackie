"""LangGraph workflow for Graph 2: Execute, Triage, Verify, and Report."""

import traceback
from datetime import datetime, timezone
from typing import Any, Dict, TypedDict

from langgraph.graph import END, StateGraph

from app.config import settings
from app.graphs import stubs
from app.models import BugsFile, Catalog
from app import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExecuteState(TypedDict):
    runId: str


def _safe_wrapper(node_name: str, fn):
    def wrapper(state: ExecuteState) -> ExecuteState:
        run_id = state.get("runId", "")
        try:
            run = storage.get_run(run_id)
            if run.stage == "failed":
                return state
            fn(run_id)
            return state
        except KeyboardInterrupt:
            raise
        except Exception as e:
            err_log = storage.run_dir(run_id) / "error.log"
            with open(err_log, "a", encoding="utf-8") as f:
                f.write(f"\n--- {node_name} failed at {_now_iso()} ---\n")
                f.write(traceback.format_exc())
            storage.fail_run(run_id, f"{node_name} failed: {e}")
            return state

    return wrapper


def _log(run_id: str, message: str, level: str = "info"):
    try:
        from app.frontend_adapter import log_pipeline
        log_pipeline(run_id, message, level=level, source="pipeline")
    except Exception:
        pass


def node_write_scripts(run_id: str) -> None:
    _log(run_id, "Pipeline: Beginning script synthesis phase for approved test catalog...")
    if settings.STUB_MODE:
        stubs.stub_write_scripts(run_id)
    else:
        from app.agents import script_writer
        script_writer.write_scripts(run_id)


def node_run_tests(run_id: str) -> None:
    storage.set_stage(run_id, "running", step="Executing Playwright test suite")
    _log(run_id, "Pipeline: Executing test suite in Playwright Chromium sandboxes...")
    if settings.STUB_MODE:
        stubs.stub_run_tests(run_id)
    else:
        from app import runner_client
        runner_client.run_tests(run_id, workers=2)
        runner_client.triage(run_id)


def node_report_bugs(run_id: str) -> None:
    storage.set_stage(run_id, "verifying", step="Writing bug reports")
    _log(run_id, "Pipeline: Writing defect reports from assertion failures...")
    if settings.STUB_MODE:
        stubs.stub_report_bugs(run_id)
    else:
        bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
        if bugs_file and bugs_file.bugs:
            from app.agents import bug_reporter
            bug_reporter.write_bug_reports(run_id)


def node_verify(run_id: str) -> None:
    storage.set_stage(run_id, "verifying", step="Replaying bugs")
    _log(run_id, "Pipeline: Starting deterministic 3x defect verification replays...")
    if settings.STUB_MODE:
        stubs.stub_verify(run_id)
    else:
        from app import verifier
        verifier.verify_all(run_id)


def node_build_report(run_id: str) -> None:
    storage.set_stage(run_id, "reporting", step="Compiling final report and metrics")
    _log(run_id, "Pipeline: Compiling final test coverage metrics and QA executive report...")
    if settings.STUB_MODE:
        stubs.stub_build_report(run_id)
    else:
        from app import report
        report.build_metrics(run_id)
        report.build_report(run_id)

    storage.set_stage(run_id, "done", step="Run completed successfully")
    _log(run_id, "Pipeline: QA execution workflow finished successfully.")


def should_continue(state: ExecuteState) -> str:
    run_id = state.get("runId", "")
    try:
        run = storage.get_run(run_id)
        if run.stage == "failed":
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


def run_execute(run_id: str) -> None:
    """Run Graph 2: scripts -> run -> triage -> bug reports -> verify -> report."""
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    if not catalog or not any(t.status == "approved" for t in catalog.tests):
        storage.fail_run(run_id, "No approved tests to execute")
        return

    global _graph2
    if _graph2 is None:
        _graph2 = build_execute_graph()
    _graph2.invoke({"runId": run_id})
