"""LangGraph workflows for explore-plan and execution pipelines.

Implemented by Track B.
"""

from app.graphs.execute import build_execute_graph, run_execute
from app.graphs.explore_plan import build_explore_plan_graph, run_explore_plan
from app import storage


def run_pipeline(run_id: str) -> None:
    """Run full pipeline: explore_plan followed by execute in autonomous mode."""
    run_explore_plan(run_id)

    # Check if autonomous mode continues straight to execution
    run = storage.get_run(run_id)
    if run.mode == "autonomous" and run.stage != "failed":
        run_execute(run_id)


__all__ = [
    "build_explore_plan_graph",
    "build_execute_graph",
    "run_explore_plan",
    "run_execute",
    "run_pipeline",
]
