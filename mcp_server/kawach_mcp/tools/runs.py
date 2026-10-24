"""Run lifecycle tools: list, inspect, start, resume, cancel, retry, delete."""

from typing import Annotated, Optional

from pydantic import Field

from ..checks import run_target_check, validate_budgets, validate_mode, validate_url_shape
from ..client import get_client
from ..errors import KawachError, add_secret
from ..formatting import STAGE_MEANING, STAGES, hint, listing, short_run
from . import CONFIRM_MESSAGE, DESTRUCTIVE, READ, WRITE, tool
from .system import upload_spec

RID = Annotated[str, Field(description="Run id, from list_runs or start_run")]

_STAGE_HINTS = {
    "awaiting_review": "Review the catalog with get_catalog, then review_tests or approve_all_and_resume; approving starts execution (no separate resume step).",
    "done": "Run finished: inspect bugs and the report.",
    "failed": "Run failed. You can retry_run, or start_run again.",
}


async def _fetch_run(run_id: str) -> dict:
    return await get_client().get(f"/runs/{run_id}")


@tool(READ)
async def list_runs(
    project_id: Annotated[Optional[str], Field(description="Only runs of this project")] = None,
    stage: Annotated[Optional[str], Field(description=f"Only runs in this stage: {', '.join(STAGES)}")] = None,
    limit: Annotated[int, Field(ge=1, le=200, description="Max runs to return")] = 20,
) -> dict:
    """List test runs, newest first, optionally for one project or stage.

    Returns compact rows {run_id, target_url, stage, mode, created_at, progress_percent, metrics}.
    Next: get_run for one run; use stage="awaiting_review" to find runs that need approval.
    """
    if stage is not None and stage not in STAGES:
        raise KawachError(f"Invalid stage {stage!r}: must be one of {', '.join(STAGES)}.")
    runs = await get_client().get("/runs", params={"project_id": project_id})
    if stage:
        runs = [r for r in runs if r.get("stage") == stage]
    runs = sorted(runs, key=lambda r: r.get("created_at") or "", reverse=True)
    return listing("runs", [short_run(r) for r in runs], limit)


@tool(READ)
async def get_run(run_id: RID) -> dict:
    """Get the full state of one run: stage (with a plain-language meaning), progress, metrics, budgets.

    Use it to follow a run or decide the next action. The backend reports progress as a percentage;
    current_step is filled in best-effort from the live execution state.
    """
    client = get_client()
    r = await _fetch_run(run_id)
    stage = r.get("stage")
    step = None
    try:
        ex = await client.get(f"/runs/{run_id}/execution")
        workers = ex.get("workers") or []
        step = next((w.get("current_step") for w in workers if w.get("status") not in (None, "idle")), None)
    except KawachError as e:
        if e.kind == "unreachable":
            raise
    out = short_run(r)
    out.update({
        "status": r.get("status"),
        "progress": {"stage": stage, "percent": r.get("progress"), "step": step},
        "finished_at": r.get("finished_at"),
        "duration_seconds": r.get("duration_seconds"),
        "prompt": r.get("prompt") or None,
        "budgets": r.get("budgets"),
        "budget_usage": r.get("budget_usage"),
        "meaning": STAGE_MEANING.get(stage, "Unknown stage."),
    })
    if stage in _STAGE_HINTS:
        out["next_step_hint"] = hint(_STAGE_HINTS[stage])
    return out


@tool(WRITE)
async def start_run(
    target_url: Annotated[Optional[str], Field(description="App URL to test; optional if project_id is given")] = None,
    project_id: Annotated[Optional[str], Field(description="Project to run against (uses its URL and default mode)")] = None,
    review_mode: Annotated[Optional[str], Field(
        description="manual (stop at awaiting_review for approval) or autonomous. Default: the project's mode, else manual")] = None,
    prompt: Annotated[Optional[str], Field(description="Natural-language focus for the testing, e.g. 'focus on checkout'")] = None,
    spec_id: Annotated[Optional[str], Field(description="Id from upload_spec")] = None,
    spec_text: Annotated[Optional[str], Field(description="Inline spec/requirements text")] = None,
    spec_file_path: Annotated[Optional[str], Field(description="Local spec file to upload first")] = None,
    budgets: Annotated[Optional[dict], Field(description="Optional budgets, see get_defaults for ranges")] = None,
    username: Annotated[Optional[str], Field(description="Login username for the app under test")] = None,
    password: Annotated[Optional[str], Field(description="Login password for the app under test")] = None,
) -> dict:
    """Start a QA run: the platform explores the app, plans tests, runs them and verifies bugs.

    Needs target_url or project_id. Provide at most one of spec_id, spec_text, spec_file_path. If the app
    needs a login pass username and password (stored project credentials are NOT applied by the backend).
    The target is safety-checked first and the run is aborted if disallowed. Returns
    {run_id, stage, mode, target_url, next_step_hint}. In manual mode the run stops at awaiting_review.
    """
    client = get_client()
    if not target_url and not project_id:
        raise KawachError("Provide target_url or project_id.")
    if sum(bool(x) for x in (spec_id, spec_text, spec_file_path)) > 1:
        raise KawachError("Provide only one of spec_id, spec_text or spec_file_path.")
    if review_mode is not None:
        validate_mode(review_mode)
    if bool(username) != bool(password):
        raise KawachError("Provide both username and password, or neither.")
    if target_url:
        validate_url_shape(target_url)
    if password:
        add_secret(password)
    await validate_budgets(client, budgets)

    mode = review_mode
    if project_id:
        proj = await client.get(f"/projects/{project_id}")
        target_url = target_url or proj.get("targetUrl")
        mode = mode or proj.get("defaultMode")
    mode = validate_mode(mode or "manual")
    target_url = validate_url_shape(target_url)

    check = await run_target_check(client, target_url)
    if not check["allowed"]:
        raise KawachError(f"Run aborted, target not allowed: {check['verdict']}. {check.get('reason') or ''}".strip())

    if spec_file_path:
        spec_id = (await upload_spec(spec_file_path))["spec_id"]

    body = {"target_url": target_url, "review_mode": mode, "prompt": prompt or ""}
    if project_id:
        body["project_id"] = project_id
    if spec_id:
        body["spec_id"] = spec_id
    if spec_text:
        body["spec_text"] = spec_text
    if budgets:
        body["budgets"] = budgets
    if username and password:
        body["credentials"] = {"username": username, "password": password}
    run = await client.post("/runs", body)
    next_hint = ("Manual mode: the run will stop at awaiting_review. Call wait_for_run to follow it, then review "
                 "the catalog (get_catalog, then review_tests or approve_all_and_resume). Approving starts execution; "
                 "no separate resume step is needed." if mode == "manual"
                 else "Autonomous mode: it runs end to end. Call wait_for_run (or get_run) to follow it.")
    return {
        "run_id": run.get("runId") or run.get("id"),
        "stage": run.get("stage"),
        "mode": run.get("review_mode") or mode,
        "target_url": run.get("targetUrl") or target_url,
        "target_check": check["verdict"],
        "next_step_hint": hint(next_hint),
    }


@tool(WRITE)
async def resume_run(run_id: RID) -> dict:
    """Low-level: force a run in awaiting_review into scripting/execution WITHOUT recording any approvals.

    Prefer review_tests or approve_all_and_resume: in this backend approving tests already starts execution, so
    no separate resume is needed, and resume_run skips the audit trail. Only valid while awaiting_review.
    Returns {run_id, stage, next_step_hint}.
    """
    r = await _fetch_run(run_id)
    if r.get("stage") != "awaiting_review":
        raise KawachError(f"Run {run_id} is in stage '{r.get('stage')}', not 'awaiting_review', so it cannot be "
                          "resumed. Use get_run to see what it is doing.", 409)
    res = await get_client().post(f"/runs/{run_id}/resume")
    return {"run_id": run_id, "stage": res.get("stage"),
            "next_step_hint": hint("Execution has started. Call get_run to follow it until stage is done.")}


@tool(DESTRUCTIVE)
async def cancel_run(
    run_id: RID,
    confirm: Annotated[bool, Field(description="Must be true to actually cancel")] = False,
) -> dict:
    """Cancel an active run. Destructive: ask the user first, then call with confirm=true.

    Without confirm=true nothing happens.
    """
    if confirm is not True:
        return dict(CONFIRM_MESSAGE)
    res = await get_client().post(f"/runs/{run_id}/cancel")
    return {"done": True, "run_id": run_id, "stage": res.get("stage")}


@tool(WRITE)
async def retry_run(run_id: RID) -> dict:
    """Retry a run that failed or was cancelled, re-running execution from its current artifacts.

    Only meaningful for stage failed or cancelled; for other stages an explanatory error is returned.
    """
    r = await _fetch_run(run_id)
    if r.get("stage") not in ("failed", "cancelled"):
        raise KawachError(f"Run {run_id} is in stage '{r.get('stage')}'. Retry only applies to failed or "
                          "cancelled runs; use get_run to follow it, or start_run for a new run.", 409)
    res = await get_client().post(f"/runs/{run_id}/retry")
    return {"run_id": run_id, "stage": res.get("stage"),
            "next_step_hint": hint("Call get_run to follow the retried run.")}


@tool(DESTRUCTIVE)
async def delete_run(
    run_id: RID,
    confirm: Annotated[bool, Field(description="Must be true to actually delete")] = False,
) -> dict:
    """Permanently delete a run, including its artifacts, logs and evidence. Destructive: confirm first.

    Without confirm=true nothing happens.
    """
    if confirm is not True:
        return dict(CONFIRM_MESSAGE)
    await get_client().delete(f"/runs/{run_id}")
    return {"done": True, "run_id": run_id, "message": "Run, artifacts and logs were deleted."}
