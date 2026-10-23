"""Action MCP tools for starting runs, approving test catalogs, and running regressions."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
import mcp.types as types
from pydantic import BaseModel, Field

from kawach_mcp.client import KawachAPIError, KawachClient
from kawach_mcp.config import Settings
from kawach_mcp.tools.registry import register_tool

ACTION_ANNOTATIONS = types.ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=True,
)


class RunHandleResponse(BaseModel):
    run_id: str = Field(description="Unique identifier for the initiated test run")
    status: str = Field(description="Execution status ('running', 'queued')")
    stage: str = Field(description="Initial workflow stage (e.g. 'exploring', 'executing')")
    target_url: str = Field(description="Web application URL under test")
    sse_url: str = Field(description="Live SSE stream endpoint for real-time progress events")


class RegressionRunHandleResponse(BaseModel):
    run_id: str = Field(description="Unique identifier for the regression run")
    project_id: str = Field(description="Target project ID")
    status: str = Field(description="Status of the regression run")
    selected_tests_count: int = Field(description="Number of saved tests selected by diff-awareness or manual filter")
    selected_test_ids: List[str] = Field(default_factory=list, description="IDs of selected saved tests")


class WaitForRunResponse(BaseModel):
    run_id: str = Field(description="Run ID that was monitored")
    status: str = Field(description="Status at end of wait period ('completed', 'failed', 'running')")
    stage: str = Field(description="Workflow stage reached")
    progress: float = Field(description="Progress percentage (0.0 to 100.0)")
    completed: bool = Field(description="True if run concluded; false if wait timed out")
    confirmed_bugs: int = Field(default=0, description="Count of confirmed deterministic defects verified 3x")
    flaky_bugs: int = 0
    message: str = Field(description="Summary message describing outcome or timeout")


@register_tool(
    name="start_run",
    description="Start an autonomous or manual exploratory test run on a target web application.",
    required_scope="runs:write",
    is_write=False,  # Operational action, does not mutate repo/code
    annotations=ACTION_ANNOTATIONS,
)
def make_start_run(client: KawachClient, settings: Settings):
    async def start_run(
        target_url: str,
        spec_text: Optional[str] = None,
        mode: str = "autonomous",
        depth_budget: int = 3,
        breadth_budget: int = 50,
        idempotency_key: Optional[str] = None,
    ) -> RunHandleResponse:
        payload = {
            "target_url": target_url,
            "spec_text": spec_text,
            "mode": mode,
            "depth_budget": depth_budget,
            "breadth_budget": breadth_budget,
        }
        res = await client.post("/api/v1/runs", json_data=payload, idempotency_key=idempotency_key)
        run_id = str(res.get("id"))
        return RunHandleResponse(
            run_id=run_id,
            status=res.get("status", "running"),
            stage=res.get("stage", "init"),
            target_url=target_url,
            sse_url=f"{settings.clean_api_url}/api/v1/runs/{run_id}/stream",
        )
    return start_run


@register_tool(
    name="approve_catalog",
    description="Approve planned test catalog and trigger parallel execution (Graph 2).",
    required_scope="runs:write",
    is_write=False,
    annotations=ACTION_ANNOTATIONS,
)
def make_approve_catalog(client: KawachClient, settings: Settings):
    async def approve_catalog(run_id: str) -> RunHandleResponse:
        res = await client.post(f"/api/v1/runs/{run_id}/execute")
        return RunHandleResponse(
            run_id=run_id,
            status=res.get("status", "running"),
            stage=res.get("stage", "executing"),
            target_url=res.get("target_url", ""),
            sse_url=f"{settings.clean_api_url}/api/v1/runs/{run_id}/stream",
        )
    return approve_catalog


@register_tool(
    name="run_regression",
    description="Trigger diff-aware or manual regression run of saved Playwright test suites.",
    required_scope="runs:write",
    is_write=False,
    annotations=ACTION_ANNOTATIONS,
)
def make_run_regression(client: KawachClient, settings: Settings):
    async def run_regression(
        project_id: str,
        test_ids: Optional[List[str]] = None,
        commit_sha: Optional[str] = None,
        files_changed: Optional[List[str]] = None,
        force_full: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> RegressionRunHandleResponse:
        payload = {
            "test_ids": test_ids,
            "commit_sha": commit_sha,
            "files_changed": files_changed,
            "force_full": force_full,
        }
        res = await client.post(
            f"/api/v1/projects/{project_id}/regression-runs",
            json_data=payload,
            idempotency_key=idempotency_key,
        )
        selected = res.get("selected_test_ids", test_ids or [])
        return RegressionRunHandleResponse(
            run_id=str(res.get("run_id")),
            project_id=project_id,
            status=res.get("status", "running"),
            selected_tests_count=len(selected),
            selected_test_ids=selected,
        )
    return run_regression


@register_tool(
    name="wait_for_run",
    description="Poll a run until completion or max wait timeout (up to 120s); returns final status and confirmed defect counts.",
    required_scope="runs:read",
    is_write=False,
    annotations=types.ToolAnnotations(read_only_hint=True),
)
def make_wait_for_run(client: KawachClient, settings: Settings):
    async def wait_for_run(
        run_id: str,
        timeout_seconds: int = 60,
        poll_interval_seconds: int = 3,
    ) -> WaitForRunResponse:
        # Cap wait duration to 120s to prevent hanging IDE agent turns
        max_duration = min(max(timeout_seconds, 1), 120)
        interval = max(poll_interval_seconds, 1)
        elapsed = 0

        last_status = "running"
        last_stage = "init"
        progress = 0.0
        confirmed = 0
        flaky = 0

        while elapsed < max_duration:
            r = await client.get(f"/api/v1/runs/{run_id}")
            last_status = r.get("status", "running")
            last_stage = r.get("stage", "init")
            progress = float(r.get("current_progress", r.get("currentProgress", 0.0)))
            confirmed = r.get("confirmed_bugs", r.get("confirmedBugs", 0))
            flaky = r.get("flaky_bugs", r.get("flakyBugs", 0))

            if last_status in ("completed", "failed", "cancelled"):
                return WaitForRunResponse(
                    run_id=run_id,
                    status=last_status,
                    stage=last_stage,
                    progress=progress,
                    completed=True,
                    confirmed_bugs=confirmed,
                    flaky_bugs=flaky,
                    message=f"Run reached terminal state: {last_status} at stage {last_stage}.",
                )

            await asyncio.sleep(interval)
            elapsed += interval

        return WaitForRunResponse(
            run_id=run_id,
            status=last_status,
            stage=last_stage,
            progress=progress,
            completed=False,
            confirmed_bugs=confirmed,
            flaky_bugs=flaky,
            message=f"Wait period of {max_duration}s elapsed while run is still {last_status} (progress: {progress:.1f}%). Use get_run_status to poll again.",
        )
    return wait_for_run
