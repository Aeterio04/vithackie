"""System, auth-info, target-check and spec-upload tools."""

import mimetypes
from pathlib import Path
from typing import Annotated

from pydantic import Field

from ..checks import run_target_check
from ..client import get_client
from ..errors import KawachError
from ..formatting import hint, trim
from . import READ, WRITE, tool


@tool(READ)
async def health_check() -> dict:
    """Check whether the KAWACH backend is up and how busy it is.

    Use this first when anything seems wrong, or before starting a run. Returns
    {status, workers_up, queue_depth, message, backend_url}. If the backend cannot be reached this
    returns status "unreachable" instead of failing. Next: whoami, then list_projects.
    """
    client = get_client()
    try:
        data = await client.get("/health", auth=False)  # open route: never needs (or triggers) a login
    except KawachError as e:
        if e.kind not in ("unreachable", "timeout"):
            raise
        return {
            "status": "unreachable", "workers_up": None, "queue_depth": None,
            "message": str(e), "backend_url": client.base_url,
            "next_step_hint": hint("Start the KAWACH backend (default http://localhost:8000), then call health_check again."),
        }
    return {
        "status": data.get("status", "unknown"),
        "workers_up": data.get("workers_up"),
        "queue_depth": data.get("queue_depth"),
        "message": data.get("message"),
        "backend_url": client.base_url,
    }


@tool(READ)
async def get_defaults() -> dict:
    """Get the platform's default test budgets, allowed ranges and spec upload rules.

    Use before creating a project or starting a run with custom budgets, or before upload_spec.
    Returns {default_budgets, limits, accepted_spec_extensions, max_spec_file_size_mb, allowed_hosts}.
    """
    d = await get_client().get_defaults()
    return {
        "default_budgets": d.get("default_budgets"),
        "limits": d.get("limits"),
        "accepted_spec_extensions": d.get("accepted_spec_extensions"),
        "max_spec_file_size_mb": d.get("max_spec_file_size_mb"),
        "allowed_hosts": d.get("allowedHosts"),
    }


@tool(READ)
async def get_stats() -> dict:
    """Get platform-wide counters: total runs, confirmed bugs, flaky bugs, pending reviews.

    Note: the backend computes these across all stored runs, not just this account's. For one run
    use get_run. Returns {total_runs, confirmed_bugs, flaky_bugs, pending_reviews}.
    """
    d = await get_client().get("/stats")
    return {k: d.get(k) for k in ("total_runs", "confirmed_bugs", "flaky_bugs", "pending_reviews")}


@tool(READ)
async def check_target(
    target_url: Annotated[str, Field(description="Full URL of the app to test, e.g. http://localhost:3000")],
) -> dict:
    """Check whether a target URL may be tested (SSRF/allow-list policy) before using it.

    Use before create_project or start_run (both also run this check themselves). Returns
    {allowed, reachable, host, status_code, reason, verdict}; verdict is one of "OK to test",
    "Blocked by SSRF policy", "Unreachable, is the app running?", "Invalid target URL".
    """
    return await run_target_check(get_client(), target_url)


@tool(WRITE)
async def upload_spec(
    file_path: Annotated[str, Field(description="Path to a local spec file (.md .txt .pdf .json .yaml .yml)")],
) -> dict:
    """Upload a local spec/requirements file so a run can generate spec-driven tests.

    Validates the file exists, has an accepted extension and is under the size limit, then uploads it.
    Returns {spec_id, filename, items_count, preview}. Next: start_run with spec_id (or pass
    spec_file_path to start_run directly). The backend keeps specs in memory only, so use the
    spec_id soon and re-upload after a backend restart.
    """
    client = get_client()
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise KawachError(f"Spec file not found: {file_path}")
    defaults = await client.get_defaults()
    exts = [e.lower() for e in defaults.get("accepted_spec_extensions", [])]
    if exts and path.suffix.lower() not in exts:
        raise KawachError(f"Unsupported spec extension {path.suffix!r}. Accepted: {', '.join(exts)}.")
    max_mb = defaults.get("max_spec_file_size_mb")
    size = path.stat().st_size
    if max_mb and size > max_mb * 1024 * 1024:
        raise KawachError(f"Spec file is {size / 1048576:.1f} MB; the limit is {max_mb} MB.")
    content = path.read_bytes()
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    res = await client.post_multipart("/specs/upload", files={"file": (path.name, content, ctype)})
    text_like = path.suffix.lower() in (".md", ".txt", ".json", ".yaml", ".yml")
    preview = trim(content.decode("utf-8", errors="replace"), 300) if text_like else "(binary file, no preview)"
    return {
        "spec_id": res.get("spec_id"),
        "filename": res.get("filename", path.name),
        "items_count": res.get("item_count"),
        "preview": preview,
        "next_step_hint": hint("Call start_run with this spec_id."),
    }


@tool(READ)
async def whoami() -> dict:
    """Show how this MCP server authenticates and who it is acting as. Never shows secrets.

    Returns {auth_mode (token|login|guest), authenticated, email, user, backend_url, download_dir, note}.
    `email` is the KAWACH account everything you do is stored under: it is the same account whose dashboard you
    see on the website after signing in with that email.
    Use it to debug "authentication failed" or to confirm which account owns the data you see.
    """
    client = get_client()
    s = client.settings
    out = {"auth_mode": s.auth_mode, "authenticated": False, "email": None, "user": None,
           "backend_url": client.base_url, "download_dir": str(s.download_dir)}
    if s.auth_mode == "guest":
        out["note"] = ("No credentials configured. Set KAWACH_EMAIL and KAWACH_PASSWORD to the account you registered "
                       "on the website (the backend has no shared guest workspace, so calls will fail with 401).")
    try:
        me = await client.get("/auth/me")
        out["authenticated"] = True
        out["user"] = {k: me.get(k) for k in ("id", "email", "displayName", "role")}
        out["email"] = me.get("email")
    except KawachError as e:
        if e.kind == "unreachable":
            raise
        out["note"] = out.get("note") or str(e)
    return out
