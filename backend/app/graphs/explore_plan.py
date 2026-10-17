"""LangGraph workflow for Graph 1: Explore and Plan."""

import traceback
from datetime import datetime, timezone
from typing import Any, Dict, TypedDict

from langgraph.graph import END, StateGraph

from app.config import settings
from app.graphs import stubs
from app import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExplorePlanState(TypedDict):
    runId: str


def _safe_wrapper(node_name: str, fn):
    def wrapper(state: ExplorePlanState) -> ExplorePlanState:
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


def node_explore(run_id: str) -> None:
    if settings.STUB_MODE:
        stubs.stub_explore(run_id)
    else:
        from app.agents import explorer
        explorer.run_explorer(run_id)


def node_plan(run_id: str) -> None:
    if settings.STUB_MODE:
        stubs.stub_plan(run_id)
    else:
        from app.agents import planner
        planner.plan_catalog(run_id)


def node_review_gate(run_id: str) -> None:
    run = storage.get_run(run_id)
    if run.mode == "manual":
        storage.set_stage(run_id, "awaiting_review", step="Waiting for the QA engineer")
        return

    # Autonomous mode
    if settings.STUB_MODE:
        stubs.stub_review_gate(run_id)
    else:
        from app.agents import reviewer
        storage.set_stage(run_id, "planning", step="Reviewer agent is checking the catalog")
        try:
            reviewer.review_catalog(run_id)
        except NotImplementedError:
            # Fallback auto-approve
            from app.models import Catalog, ReviewDecision, ReviewLog
            catalog = storage.load_model(run_id, "catalog.json", Catalog)
            decisions = []
            if catalog:
                for t in catalog.tests:
                    if t.status == "proposed":
                        t.status = "approved"
                        decisions.append(
                            ReviewDecision(
                                testId=t.id,
                                decision="approve",
                                reason="Auto-approved: reviewer not available",
                            )
                        )
                storage.save_model(run_id, "catalog.json", catalog)
            storage.save_model(
                run_id,
                "review_log.json",
                ReviewLog(runId=run_id, reviewedAt=_now_iso(), decisions=decisions),
            )

        storage.set_stage(run_id, "scripting", step="Review done")


def should_continue(state: ExplorePlanState) -> str:
    run_id = state.get("runId", "")
    try:
        run = storage.get_run(run_id)
        if run.stage == "failed":
            return "failed"
    except Exception:
        return "failed"
    return "ok"


def build_explore_plan_graph():
    """Build and compile Graph 1 (Explore -> Plan -> Review Gate)."""
    builder = StateGraph(ExplorePlanState)

    builder.add_node("explore", _safe_wrapper("explore", node_explore))
    builder.add_node("plan", _safe_wrapper("plan", node_plan))
    builder.add_node("review_gate", _safe_wrapper("review_gate", node_review_gate))

    builder.set_entry_point("explore")

    builder.add_conditional_edges(
        "explore",
        should_continue,
        {"ok": "plan", "failed": END},
    )
    builder.add_conditional_edges(
        "plan",
        should_continue,
        {"ok": "review_gate", "failed": END},
    )
    builder.add_edge("review_gate", END)

    return builder.compile()


_graph1 = None


def run_explore_plan(run_id: str) -> None:
    """Run Graph 1: explore -> plan -> review_gate."""
    global _graph1
    if _graph1 is None:
        _graph1 = build_explore_plan_graph()
    _graph1.invoke({"runId": run_id})
