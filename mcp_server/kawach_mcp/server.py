"""FastMCP server construction."""

import asyncio
import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from . import __version__
from .client import get_client
from .config import get_settings
from .prompts import register_prompts
from .resources import register_resources
from .tools import bugs, catalog, observe, projects, register_module, reports, runs, system, workflow

log = logging.getLogger("kawach_mcp.server")

SERVER_NAME = "kawach-qa"

INSTRUCTIONS = """KAWACH is an autonomous AI QA platform. Use these tools to test a web app, review the plan, read VERIFIED bugs,
fix the code and retest.

Typical order: health_check -> whoami -> (create_project | list_projects) -> run_qa_pipeline (or start_run) ->
wait_for_run -> [review gate] -> get_run_summary -> list_bugs / get_bug_fix_context -> fix the code ->
save_repro_script -> retest_after_fix -> compare_runs.

Review gate: in manual mode a run stops at stage 'awaiting_review'. Look at get_catalog, then review_tests (rejections need a
reason) or approve_all_and_resume. In this backend approving tests starts execution at once; there is no separate resume step.
Autonomous mode has no gate.

Bug honesty: a bug is CONFIRMED only when 3 of 3 deterministic replays reproduce it. Flaky (1/3, 2/3), not-reproduced (0/3) and
unverified candidates are never confirmed defects; always report them separately.

Long runs: wait_for_run and run_qa_pipeline return still_running=true instead of failing when time is up; just call wait_for_run
again. Destructive tools (delete_run, cancel_run, delete_project, delete_saved_test) do nothing without confirm=true: ask the
user first. Never put passwords in prompts or messages; credentials come from the server's environment."""


async def probe_backend() -> dict:
    """Non-blocking startup probe: never raises, never delays startup for more than a few seconds."""
    try:
        return await asyncio.wait_for(system.health_check(), timeout=5)
    except Exception as e:  # noqa: BLE001 - a failed probe must not prevent startup
        return {"status": "unreachable", "message": type(e).__name__}


@asynccontextmanager
async def _lifespan(_server: FastMCP):
    s = get_settings()
    probe = await probe_backend()
    log.info("kawach-mcp %s | backend %s | auth mode %s | download dir %s | health probe: %s",
             __version__, s.base_url, s.auth_mode, s.download_dir, probe.get("status"))
    if probe.get("status") == "unreachable":
        log.warning("Backend not reachable yet; tools will report it and work again once it is up.")
    try:
        yield {}
    finally:
        await get_client().aclose()  # graceful shutdown


def create_server(host: str = "127.0.0.1", port: int = 8765) -> FastMCP:
    mcp = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS, lifespan=_lifespan, host=host, port=port)
    try:
        mcp._mcp_server.version = __version__  # report the package version as serverInfo.version
    except Exception:  # noqa: BLE001
        pass
    for module in (system, projects, runs, catalog, bugs, observe, reports, workflow):
        register_module(mcp, module)
    register_resources(mcp)
    register_prompts(mcp)
    return mcp
