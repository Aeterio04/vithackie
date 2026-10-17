"""LangGraph workflows for explore-plan and execution pipelines.

Implemented by Track B.
"""


def run_explore_plan(run_id: str) -> None:
    """Run Graph 1: explore -> plan -> review gate.

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements run_explore_plan")


def run_execute(run_id: str) -> None:
    """Run Graph 2: script -> run -> triage -> report bugs -> verify -> report.

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements run_execute")


def run_pipeline(run_id: str) -> None:
    """Run full pipeline (explore_plan followed by execute in autonomous mode).

    Implemented by Track B.
    """
    raise NotImplementedError("Track B implements run_pipeline")
