"""Project, credential and Project Manager (saved tests, commits) tools."""

from typing import Annotated, Any, Optional

from pydantic import Field

from ..checks import (project_body, require_nonempty, run_target_check, validate_budgets, validate_mode,
                      validate_url_shape)
from ..client import get_client
from ..errors import KawachError, add_secret
from ..formatting import hint, listing, short_project, short_run, trim
from . import CONFIRM_MESSAGE, DESTRUCTIVE, IDEMPOTENT_WRITE, READ, WRITE, tool

PID = Annotated[str, Field(description="Project id, from list_projects")]
Budgets = Annotated[Optional[dict], Field(
    description="Optional budgets, e.g. {\"max_pages\": 10, \"max_steps_per_test\": 30, "
                "\"max_run_minutes\": 15, \"parallel_workers\": 2}. Ranges come from get_defaults.")]


def _full_project(p: dict) -> dict:
    out = short_project(p)
    out.update({
        "description": p.get("description"),
        "budgets": p.get("budgets") or {},
        "allowed_hosts": p.get("allowedHosts") or [],
        "spec_version": p.get("specVersion"),
        "pat_masked": p.get("patMasked") or None,
        "created_at": p.get("createdAt"),
        "updated_at": p.get("updatedAt"),
        "archived_at": p.get("archivedAt"),
    })
    return out


@tool(READ)
async def list_projects(
    limit: Annotated[int, Field(ge=1, le=200, description="Max projects to return")] = 50,
) -> dict:
    """List the projects (test targets) in this account.

    Returns compact rows {id, name, target_url, default_mode, saved_test_count, last_run_status,
    github_url}. Next: get_project for details, start_run(project_id=...) to test one, or create_project.
    """
    rows = [short_project(p) for p in await get_client().get("/projects")]
    return listing("projects", rows, limit)


@tool(READ)
async def get_project(project_id: PID) -> dict:
    """Get one project in full: URL, mode, budgets, GitHub link, saved test count.

    Secrets are never returned (the GitHub token is shown masked only). Next: list_runs(project_id=...)
    or start_run(project_id=...).
    """
    return _full_project(await get_client().get(f"/projects/{project_id}"))


@tool(WRITE)
async def create_project(
    name: Annotated[str, Field(description="Project name")],
    target_url: Annotated[str, Field(description="URL of the app under test, e.g. http://localhost:3000")],
    description: Annotated[Optional[str], Field(description="Short description")] = None,
    default_mode: Annotated[str, Field(description="manual (human approves the catalog) or autonomous")] = "manual",
    budgets: Budgets = None,
    github_url: Annotated[Optional[str], Field(description="GitHub repo URL for commit/regression features")] = None,
) -> dict:
    """Create a project for a target app. Runs the target safety check first.

    Blocks creation if the target is disallowed by the SSRF/allow-list policy; an unreachable app only
    produces a warning. Returns {project, target_check, next_step_hint}. Next: set_project_credentials
    if the app needs a login, then start_run(project_id=...).
    """
    client = get_client()
    name = require_nonempty(name, "name")
    validate_url_shape(target_url)
    validate_mode(default_mode, "default_mode")
    await validate_budgets(client, budgets)
    check = await run_target_check(client, target_url)
    if not check["allowed"]:
        raise KawachError(f"Target not allowed: {check['verdict']}. {check.get('reason') or ''}".strip())
    created = await client.post("/projects", project_body(
        name=name, target_url=target_url.strip(), description=description, default_mode=default_mode,
        budgets=budgets, github_url=github_url))
    return {
        "project": _full_project(created),
        "target_check": check,
        "next_step_hint": hint("If the app needs a login call set_project_credentials, then start_run with this project_id."),
    }


@tool(IDEMPOTENT_WRITE)
async def update_project(
    project_id: PID,
    name: Optional[str] = None,
    target_url: Optional[str] = None,
    description: Optional[str] = None,
    default_mode: Annotated[Optional[str], Field(description="manual or autonomous")] = None,
    budgets: Budgets = None,
    github_url: Optional[str] = None,
) -> dict:
    """Partially update a project; only the fields you pass change. At least one field is required.

    A new target_url goes through the same safety check as create_project. Returns the updated project.
    """
    client = get_client()
    if all(v is None for v in (name, target_url, description, default_mode, budgets, github_url)):
        raise KawachError("Nothing to update: pass at least one field to change.")
    if name is not None:
        require_nonempty(name, "name")
    if default_mode is not None:
        validate_mode(default_mode, "default_mode")
    check = None
    if target_url is not None:
        validate_url_shape(target_url)
        check = await run_target_check(client, target_url)
        if not check["allowed"]:
            raise KawachError(f"Target not allowed: {check['verdict']}. {check.get('reason') or ''}".strip())
    await validate_budgets(client, budgets)
    updated = await client.put(f"/projects/{project_id}", project_body(
        name=name, target_url=target_url, description=description, default_mode=default_mode,
        budgets=budgets, github_url=github_url))
    out = {"project": _full_project(updated)}
    if check:
        out["target_check"] = check
    return out


@tool(DESTRUCTIVE)
async def delete_project(
    project_id: PID,
    confirm: Annotated[bool, Field(description="Must be true to actually delete")] = False,
) -> dict:
    """Delete (archive) a project. Destructive: ask the user first, then call with confirm=true.

    Without confirm=true nothing happens. Returns {ok, archived}.
    """
    if confirm is not True:
        return dict(CONFIRM_MESSAGE)
    res = await get_client().delete(f"/projects/{project_id}")
    return {"ok": bool(res.get("ok", True)), "archived": True, "done": True}


@tool(READ)
async def get_project_credentials(project_id: PID) -> dict:
    """Check whether login credentials are stored for the project's target app. Never returns the password.

    Returns {has_secret, username, updated_at}. updated_at is null because the backend does not report it.
    """
    d = await get_client().get(f"/projects/{project_id}/credentials")
    return {
        "has_secret": bool(d.get("hasSecret", d.get("has_secret"))),
        "username": d.get("username") or "",
        "updated_at": d.get("updatedAt") or d.get("updated_at"),
    }


@tool(IDEMPOTENT_WRITE)
async def set_project_credentials(
    project_id: PID,
    username: Annotated[str, Field(description="Login username/email for the target app")],
    password: Annotated[str, Field(description="Login password for the target app (stored encrypted, write-only)")],
) -> dict:
    """Store login credentials for the app under test, encrypted at rest and write-only.

    Note: the backend does not auto-apply stored credentials when a run starts; also pass username and
    password to start_run for apps that need a login. Returns {ok, stored_encrypted, username}.
    """
    username = require_nonempty(username, "username")
    require_nonempty(password, "password")
    add_secret(password)
    await get_client().put(f"/projects/{project_id}/credentials", {"username": username, "password": password})
    return {"ok": True, "stored_encrypted": True, "username": username,
            "message": "Credentials were stored encrypted. The password cannot be read back."}


# ---------------- Project Manager: saved tests ----------------

def _short_saved(t: dict) -> dict:
    return {
        "id": t.get("id"), "name": t.get("name"), "tags": t.get("tags") or [],
        "is_active": t.get("is_active", True),
        "last_result": t.get("last_result") or t.get("lastResult"),
        "origin_run_id": t.get("origin_run_id"), "origin_test_id": t.get("origin_test_case_id"),
        "updated_at": t.get("updated_at"),
    }


@tool(READ)
async def list_saved_tests(
    project_id: PID,
    tag: Annotated[Optional[str], Field(description="Only tests with this tag")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> dict:
    """List a project's saved regression tests (verified tests kept for re-running).

    Returns rows {id, name, tags, last_result, origin_run_id, origin_test_id}. Next: run_saved_tests.
    """
    rows = [_short_saved(t) for t in await get_client().get(f"/projects/{project_id}/saved-tests",
                                                           params={"tag": tag})]
    return listing("saved_tests", rows, limit)


@tool(WRITE)
async def save_test_to_project(
    project_id: PID,
    run_id: Annotated[str, Field(description="Run the test came from")],
    test_id: Annotated[str, Field(description="Test case id inside that run, e.g. T01")],
    name: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Save an executed test from a run into the project's permanent regression library."""
    body = {"run_id": run_id, "test_id": test_id, "tags": tags or []}
    if name:
        body["name"] = name
    return {"saved_test": _short_saved(await get_client().post(f"/projects/{project_id}/saved-tests", body)),
            "next_step_hint": hint("Call run_saved_tests to re-run the regression library.")}


@tool(WRITE)
async def run_saved_tests(
    project_id: PID,
    test_id: Annotated[Optional[str], Field(description="Run just this saved test; omit to run all")] = None,
) -> dict:
    """Re-run saved regression tests for a project (all of them, or one by test_id) as a background run.

    Returns the backend's run info. Poll get_run / list_runs(project_id=...) to follow it.
    """
    path = (f"/projects/{project_id}/saved-tests/{test_id}/run" if test_id
            else f"/projects/{project_id}/saved-tests/run-all")
    res = await get_client().post(path)
    rid = res.get("run_id") or res.get("runId") if isinstance(res, dict) else None
    return {"started": True, "run_id": rid, "result": res,
            "next_step_hint": hint("Call get_run with run_id (or list_runs for the project) to follow progress.")}


@tool(DESTRUCTIVE)
async def delete_saved_test(
    project_id: PID,
    test_id: Annotated[str, Field(description="Saved test id from list_saved_tests")],
    confirm: Annotated[bool, Field(description="Must be true to actually delete")] = False,
) -> dict:
    """Remove a test from the project's regression library. Destructive: confirm with the user first."""
    if confirm is not True:
        return dict(CONFIRM_MESSAGE)
    await get_client().delete(f"/projects/{project_id}/saved-tests/{test_id}")
    return {"ok": True, "done": True}


# ---------------- Project Manager: commits ----------------

@tool(READ)
async def list_commits(
    project_id: PID,
    limit: Annotated[int, Field(ge=1, le=200)] = 20,
) -> dict:
    """List commit events recorded for a project (commits that triggered or could trigger regression runs)."""
    rows = [{
        "id": c.get("id"), "sha": (c.get("sha") or "")[:10], "branch": c.get("branch"),
        "author": c.get("author"), "message": trim(c.get("message"), 120), "status": c.get("status"),
        "files_changed": len(c.get("files_changed") or []), "created_at": c.get("created_at"),
    } for c in await get_client().get(f"/projects/{project_id}/commits")]
    return listing("commits", rows, limit)


@tool(READ)
async def list_github_commits(project_id: PID) -> dict:
    """List recent commits from the project's linked GitHub repo (uses the stored GitHub link and token).

    Returns {configured, message, commits}. configured=false means no valid GitHub URL is set; fix it with
    update_project(github_url=...).
    """
    d = await get_client().get(f"/projects/{project_id}/commits/github")
    commits = d.get("commits") or []
    return {"configured": bool(d.get("configured")), "message": d.get("message"),
            **listing("commits", commits, 30)}


@tool(READ)
async def get_project_overview(project_id: PID) -> dict:
    """One-call summary of a project: details, its latest runs and saved-test health.

    The backend has no overview route, so this combines get_project, the project's runs and its saved tests.
    """
    client = get_client()
    project = await client.get(f"/projects/{project_id}")
    runs: Any = await client.get(f"/projects/{project_id}/runs")
    saved: Any = await client.get(f"/projects/{project_id}/saved-tests")
    runs = sorted(runs, key=lambda r: r.get("created_at") or "", reverse=True)
    results: dict = {}
    for t in saved:
        k = t.get("last_result") or t.get("lastResult") or "never_run"
        results[k] = results.get(k, 0) + 1
    return {
        "project": _full_project(project),
        "run_count": len(runs),
        "latest_runs": [short_run(r) for r in runs[:5]],
        "saved_tests": {"total": len(saved), "by_last_result": results},
        "next_step_hint": hint("start_run to test again, or run_saved_tests to re-run the regression library."),
    }
