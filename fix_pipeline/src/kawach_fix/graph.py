"""LangGraph state machine wiring for Kawach GitHub Fix Pipeline."""

import asyncio
import time
import uuid
from typing import Any, Dict, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from kawach_fix.agents.fix_llm import run_fix_llm
from kawach_fix.agents.github_collector import run_collector
from kawach_fix.agents.pr_raiser import run_pr_raiser
from kawach_fix.agents.verifier import run_verifier
from kawach_fix.deps import Deps
from kawach_fix.redact import write_artifact
from kawach_fix.schemas import (
    CommitContext,
    FixProposal,
    FixRequest,
    FixResult,
    PullRequestInfo,
    VerificationResult,
)


class PipelineState(TypedDict, total=False):
    """Execution state passed along the LangGraph pipeline."""

    request: FixRequest
    run_id: str
    verification: Optional[VerificationResult]
    commit_context: Optional[CommitContext]
    proposal: Optional[FixProposal]
    pull_request: Optional[PullRequestInfo]
    result: Optional[FixResult]


def build_fix_graph(deps: Deps):
    """Build and compile the LangGraph state machine with dependency injection."""
    builder = StateGraph(PipelineState)

    async def node_verify(state: PipelineState) -> Dict[str, Any]:
        req = state["request"]
        run_id = state["run_id"]
        pat_str = req.github_pat.get_secret_value()

        verification, early_result = await run_verifier(req, deps.runner)
        write_artifact(
            deps.runs_dir,
            run_id,
            "verification.json",
            verification,
            extra_secrets=[pat_str],
        )

        updates: Dict[str, Any] = {"verification": verification}
        if early_result:
            updates["result"] = early_result
            write_artifact(
                deps.runs_dir,
                run_id,
                "result.json",
                early_result,
                extra_secrets=[pat_str],
            )
        return updates

    async def node_collect(state: PipelineState) -> Dict[str, Any]:
        req = state["request"]
        run_id = state["run_id"]
        verification = state["verification"]
        assert verification is not None

        pat_str = req.github_pat.get_secret_value()
        gh_client = deps.resolve_github_client(req.github_pat)

        commit_ctx, early_result = await run_collector(req, gh_client, verification)
        updates: Dict[str, Any] = {"commit_context": commit_ctx}

        if commit_ctx:
            write_artifact(
                deps.runs_dir,
                run_id,
                "commit_context.json",
                commit_ctx,
                extra_secrets=[pat_str],
            )

        if early_result:
            updates["result"] = early_result
            write_artifact(
                deps.runs_dir,
                run_id,
                "result.json",
                early_result,
                extra_secrets=[pat_str],
            )
        return updates

    async def node_propose(state: PipelineState) -> Dict[str, Any]:
        req = state["request"]
        run_id = state["run_id"]
        verification = state["verification"]
        commit_ctx = state["commit_context"]
        assert verification is not None and commit_ctx is not None

        pat_str = req.github_pat.get_secret_value()
        # Node 3 receives ONLY the LLM client, NO GitHub token
        llm_client = deps.resolve_llm_client()

        proposal, early_result, llm_req, llm_resp = await run_fix_llm(
            req, llm_client, verification, commit_ctx
        )

        write_artifact(
            deps.runs_dir,
            run_id,
            "llm_request_redacted.json",
            llm_req,
            extra_secrets=[pat_str],
        )
        write_artifact(
            deps.runs_dir,
            run_id,
            "llm_response.json",
            {"response": llm_resp},
            extra_secrets=[pat_str],
        )

        updates: Dict[str, Any] = {"proposal": proposal}
        if early_result:
            updates["result"] = early_result
            write_artifact(
                deps.runs_dir,
                run_id,
                "result.json",
                early_result,
                extra_secrets=[pat_str],
            )
        return updates

    async def node_raise_pr(state: PipelineState) -> Dict[str, Any]:
        req = state["request"]
        run_id = state["run_id"]
        verification = state["verification"]
        commit_ctx = state["commit_context"]
        proposal = state["proposal"]
        assert verification is not None and commit_ctx is not None and proposal is not None

        pat_str = req.github_pat.get_secret_value()
        gh_client = deps.resolve_github_client(req.github_pat)

        pr_info, final_result = await run_pr_raiser(
            req, gh_client, verification, commit_ctx, proposal
        )

        write_artifact(
            deps.runs_dir,
            run_id,
            "result.json",
            final_result,
            extra_secrets=[pat_str],
        )

        return {"pull_request": pr_info, "result": final_result}

    # Conditional Routing Logic
    def route_verify(state: PipelineState) -> str:
        return "end" if state.get("result") is not None else "collect"

    def route_collect(state: PipelineState) -> str:
        return "end" if state.get("result") is not None else "propose"

    def route_propose(state: PipelineState) -> str:
        return "end" if state.get("result") is not None else "raise_pr"

    builder.add_node("verify", node_verify)
    builder.add_node("collect", node_collect)
    builder.add_node("propose", node_propose)
    builder.add_node("raise_pr", node_raise_pr)

    builder.add_edge(START, "verify")
    builder.add_conditional_edges("verify", route_verify, {"collect": "collect", "end": END})
    builder.add_conditional_edges("collect", route_collect, {"propose": "propose", "end": END})
    builder.add_conditional_edges("propose", route_propose, {"raise_pr": "raise_pr", "end": END})
    builder.add_edge("raise_pr", END)

    return builder.compile()


async def arun_fix_pipeline(
    request: FixRequest, deps: Optional[Deps] = None
) -> FixResult:
    """Async entry point for executing the fix pipeline."""
    injected_deps = deps or Deps()
    run_id = request.run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    compiled_graph = build_fix_graph(injected_deps)
    initial_state: PipelineState = {
        "request": request,
        "run_id": run_id,
        "verification": None,
        "commit_context": None,
        "proposal": None,
        "pull_request": None,
        "result": None,
    }

    final_state = await compiled_graph.ainvoke(initial_state)
    result = final_state.get("result")
    if not result:
        return FixResult(
            status="fix_not_possible",
            reason="Pipeline finished without producing a terminal result.",
        )
    return result


def run_fix_pipeline(
    request: FixRequest, deps: Optional[Deps] = None
) -> FixResult:
    """Synchronous entry point for executing the fix pipeline."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(arun_fix_pipeline(request, deps))).result()
    else:
        return asyncio.run(arun_fix_pipeline(request, deps))
