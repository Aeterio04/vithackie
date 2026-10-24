"""Workflow tools: one call gives the agent a digest, a fix brief, a saved repro test, a pipeline run or a diff.

Bug trust rule: every number and label here comes from bugs.load_bugs/norm_bug, i.e. from the real verification
record (3 of 3 finished replays = confirmed). The backend's own "confirmed" label is never used on its own.
"""

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Optional
from urllib.parse import urlparse

from mcp.server.fastmcp import Context
from pydantic import Field

from ..checks import run_target_check
from ..client import get_client
from ..errors import KawachError
from ..formatting import STAGE_MEANING, TERMINAL_STAGES, hint, trim
from ..fsafe import sanitize_filename
from . import READ, WRITE, tool
from . import projects as projects_tools
from . import reports as reports_tools
from . import runs as runs_tools
from . import system as system_tools
from .bugs import fetch_verification, find_raw_bug, load_bugs, norm_bug
from .observe import wait_core

RID = Annotated[str, Field(description="Run id, from list_runs or start_run")]
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SCRIPT_LIMIT = 12000
_WAIT_STAGES = ["awaiting_review", "done", "failed", "cancelled"]
_RECOMMEND = {
    "awaiting_review": "Review the catalog (get_catalog), then review_tests or approve_all_and_resume.",
    "failed": "Read get_logs(level='error'), then consider retry_run.",
    "cancelled": "Run was cancelled; start a new run or retry_run.",
}


def _recommend(stage: str, confirmed: int) -> str:
    if stage in _RECOMMEND:
        return _RECOMMEND[stage]
    if stage == "done":
        return ("Call get_bug_fix_context for each confirmed bug." if confirmed
                else "No confirmed defects; report flaky candidates honestly.")
    return "Call wait_for_run."


def _short(r: dict) -> dict:
    return {"id": r["id"], "title": r["title"], "severity": r["severity"], "testId": r.get("testId"),
            "verification": r["verification"] + (": confirmed" if r["status"] == "confirmed" else "")}


def _counts(rows: list[dict]) -> dict:
    n = lambda s: sum(1 for r in rows if r["status"] == s)  # noqa: E731
    return {"confirmed": n("confirmed"), "flaky": n("flaky"), "not_reproduced": n("not_reproduced"),
            "unverified": sum(1 for r in rows if r["status"] not in ("confirmed", "flaky", "not_reproduced"))}


async def _metrics(run_id: str) -> Optional[dict]:
    try:
        return await reports_tools.get_metrics(run_id)
    except KawachError as e:
        if e.kind in ("unreachable", "timeout"):
            raise
        return None


async def digest(run_id: str) -> dict:
    """The get_run_summary payload (also reused by the pipeline tools)."""
    client = get_client()
    run = await client.get(f"/runs/{run_id}")
    stage = run.get("stage")
    step = None
    if stage not in TERMINAL_STAGES and stage != "awaiting_review":
        try:
            ex = await client.get(f"/runs/{run_id}/execution")
            step = next((w.get("current_step") for w in ex.get("workers") or [] if w.get("status") not in (None, "idle")), None)
        except KawachError as e:
            if e.kind in ("unreachable", "timeout"):
                raise
    m = await _metrics(run_id)
    counts = run.get("counts") or {}
    available = bool(m) and (stage in ("done", "reporting", "failed", "cancelled") or bool((m.get("tests") or {}).get("approved")))
    try:
        rows = await load_bugs(client, run_id)
    except KawachError as e:
        if e.kind in ("unreachable", "timeout"):
            raise
        rows = []
    bug_counts = _counts(rows)
    confirmed = sorted([r for r in rows if r["status"] == "confirmed"], key=lambda r: SEVERITY_RANK.get(r["severity"], 9))
    t = (m or {}).get("tests") or {}
    metrics = {
        "available": available,
        # executed tests (planned ones plus any exploratory finds) so passed + failed adds up to the total
        "total_tests": ((t.get("passed") or 0) + (t.get("failed") or 0) + (t.get("errored") or 0))
        or counts.get("total_tests", t.get("planned", 0)) or 0,
        "passed": t.get("passed") or 0, "failed": (t.get("failed") or 0) + (t.get("errored") or 0),
        "pass_rate_percent": t.get("pass_rate_percent"),
        "spec_coverage_percent": ((m or {}).get("spec_coverage") or {}).get("percent"),
        "wall_clock_seconds": (m or {}).get("wall_clock_seconds"),
        "estimated_cost_usd": ((m or {}).get("llm") or {}).get("cost_usd"),
    }
    bugs = {**bug_counts, "available": bool(rows) or stage in ("done", "reporting")}
    out = {
        "run_id": run_id, "target_url": run.get("targetUrl") or run.get("target_url"), "stage": stage,
        "mode": run.get("review_mode"), "meaning": STAGE_MEANING.get(stage),
        "progress": {"stage": stage, "percent": run.get("progress"), "step": step, "done": None, "total": None},
        "metrics": metrics, "bugs": bugs, "top_confirmed_bugs": [_short(r) for r in confirmed[:5]],
        "recommended_next_action": _recommend(stage, bug_counts["confirmed"]),
    }
    notes = []
    if bug_counts["flaky"]:
        notes.append(f"{bug_counts['flaky']} flaky candidate(s) are intermittent (1/3 or 2/3 replays) and are NOT confirmed defects.")
    if bug_counts["not_reproduced"]:
        notes.append(f"{bug_counts['not_reproduced']} candidate(s) did not reproduce (0/3).")
    if bug_counts["unverified"]:
        notes.append(f"{bug_counts['unverified']} candidate(s) have no complete 3-replay record and are NOT counted as confirmed.")
    if notes:
        out["honesty_note"] = " ".join(notes)
    out["next_step_hint"] = hint(out["recommended_next_action"])
    return out


@tool(READ)
async def get_run_summary(run_id: RID) -> dict:
    """One-call digest of a run: stage, metrics, verified bug counts and the top confirmed bugs.

    Use this instead of calling get_run, get_metrics and list_bugs separately. Bugs are counted confirmed ONLY
    with 3/3 reproductions in the real verification record; flaky, not-reproduced and unverified candidates are
    reported separately. Early in a run, metrics/bugs are zero with available=false. Returns
    {run_id, target_url, stage, mode, progress, metrics, bugs{confirmed, flaky, not_reproduced, unverified},
    top_confirmed_bugs (max 5, critical first), recommended_next_action, next_step_hint}.
    """
    return await digest(run_id)


# ---------------------------------------------------------------- fix brief

_NAV = re.compile(r"(?:navigate to|go to|open|visit)\s+(/[^\s'\"`,;)]*)", re.I)
_GOTO = re.compile(r"""page\.goto\(\s*['"`]([^'"`]+)['"`]""")
_PATHLIKE = re.compile(r"(?<![\w.:/])(/[a-z][\w\-/]*)", re.I)


def guess_page_path(steps: list, script: Optional[str], pages: list, title: str = "") -> Optional[str]:
    """Page path from the bug steps, the repro script, or the app map; None if nothing matches."""
    text = " ".join(str(s) for s in steps or [])
    if m := _NAV.search(text):
        return m.group(1)
    if script and (m := _GOTO.search(script)):
        path = urlparse(m.group(1)).path or m.group(1)
        if path.startswith("/"):
            return path
    if m := _PATHLIKE.search(text):
        return m.group(1)
    haystack = f"{title} {text}".lower()
    for p in pages or []:
        path = urlparse(p.get("url") or "").path
        seg = path.rstrip("/").rsplit("/", 1)[-1].lower()
        if seg and len(seg) > 2 and seg in haystack:
            return path
    return None


async def _raw_extras(client, run_id: str, bug_id: str) -> dict:
    """Richer fields (errorMessage, category, testId) that only the raw bugs.json carries."""
    try:
        data = json.loads(await client.get_text(f"/runs/{run_id}/files/bugs.json"))
        return next((b for b in data.get("bugs", []) if b.get("id") == bug_id), {}) or {}
    except (KawachError, ValueError, AttributeError) as e:
        if isinstance(e, KawachError) and e.kind in ("unreachable", "timeout"):
            raise
        return {}


async def _script_text(client, raw: dict) -> Optional[str]:
    url = raw.get("repro_script_url")
    if not url:
        return None
    try:
        return await client.get_text(url)
    except KawachError as e:
        if e.kind in ("unreachable", "timeout"):
            raise
        return None


@tool(READ)
async def get_bug_fix_context(
    run_id: RID,
    bug_id: Annotated[str, Field(description="Bug id from list_bugs, e.g. B01")],
    allow_unconfirmed: Annotated[bool, Field(description="Allow a brief for a flaky/not-reproduced/unverified bug (marked with a warning)")] = False,
) -> dict:
    """Build a self-contained markdown FIX BRIEF for one bug so you can fix the code without more lookups.

    Refuses bugs that are not confirmed (3/3 replays) unless allow_unconfirmed=True. The brief has the title,
    severity and verification line, the page, spec ref, steps to reproduce, expected vs actual, error and console
    output, the full Playwright repro script and fix guidance. Returns {bug_id, run_id, severity, status,
    verification, page_path, brief}. Next: fix the code in this repository, save_repro_script, retest_after_fix.
    """
    client = get_client()
    raw = await find_raw_bug(client, bug_id, run_id)
    row = norm_bug(raw, await fetch_verification(client, run_id, bug_id))
    status = row["status"]
    if status != "confirmed" and not allow_unconfirmed:
        raise KawachError(
            f"Bug {bug_id} is '{status}' ({row['verification']}), not confirmed. Only bugs with 3/3 reproductions get a fix "
            "brief by default. Pass allow_unconfirmed=True if you still want one (it will carry a warning).")
    extras = await _raw_extras(client, run_id, bug_id)
    script = await _script_text(client, raw)
    pages = []
    steps = raw.get("steps_to_reproduce") or []
    path = guess_page_path(steps, script, [], row["title"] or "")
    if path is None:
        try:
            pages = (await client.get(f"/runs/{run_id}/app-map")).get("pages") or []
        except KawachError as e:
            if e.kind in ("unreachable", "timeout"):
                raise
        path = guess_page_path(steps, script, pages, row["title"] or "")
    ev = raw.get("evidence") or {}
    err = extras.get("errorMessage")
    consoles = ev.get("console") or []
    spec = ", ".join(row["specRef"]) or "none recorded"
    lines = []
    if status != "confirmed":
        lines += [f"**WARNING: this bug is {status.upper()} ({row['verification']}). It is NOT a confirmed defect; "
                  "it may be intermittent or not real. Verify before changing code.**", ""]
    lines += [
        f"# Fix brief: {row['title']}", "",
        f"- **Bug:** {bug_id} (run {run_id}, test {row.get('testId') or extras.get('testId') or 'unknown'})",
        f"- **Severity:** {row['severity']}",
        f"- **Status:** {row['verification']}: {status}",
        f"- **Where:** {path or 'page path not recorded (use the steps below)'}"
        + (f" ({str(raw.get('target_url') or '')})" if raw.get("target_url") else ""),
        f"- **Spec reference:** {spec}", "", "## Steps to reproduce",
    ]
    lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)] or ["(no steps recorded)"]
    lines += ["", "## Expected vs actual", f"- **Expected:** {raw.get('expected') or 'not recorded'}",
              f"- **Actual:** {raw.get('actual') or 'not recorded'}", "", "## Error output"]
    lines += [f"- Error: `{trim(err, 500)}`"] if err else ["- Error message: not recorded"]
    lines += [f"- Console: `{trim(c, 300)}`" for c in consoles[:10]] or ["- Console errors: none"]
    lines += ["", "## Playwright repro script"]
    if script:
        lines += ["```ts", trim(script, SCRIPT_LIMIT), "```"]
    else:
        lines += ["(script not available from the backend)"]
    lines += ["", "## How to fix",
              f"Locate the route/component for `{path or 'the page in the steps'}` in this repository (search for the path string, "
              "form field labels or button text used in the steps). Fix the root cause in the application code, not the test. "
              "After fixing, save the repro test with save_repro_script and call retest_after_fix."]
    return {"bug_id": bug_id, "run_id": run_id, "severity": row["severity"], "status": status,
            "verification": row["verification"], "page_path": path, "brief": "\n".join(lines),
            "next_step_hint": hint("Fix the code, then save_repro_script and retest_after_fix.")}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "bug").lower()).strip("-")[:50] or "bug"


@tool(WRITE)
async def save_repro_script(
    run_id: RID,
    bug_id: Annotated[str, Field(description="Bug id from list_bugs, e.g. B01")],
    dest_dir: Annotated[str, Field(description="Folder inside the current working directory (default tests/kawach)")] = "tests/kawach",
    filename: Annotated[Optional[str], Field(description="File name; default <bug_id>-<slug>.spec.ts")] = None,
    overwrite: Annotated[bool, Field(description="Replace an existing file with the same name")] = False,
) -> dict:
    """Save a bug's full Playwright repro script into the workspace so it can guard against regressions.

    Paths resolve against the server's working directory and must stay inside it. Never overwrites unless
    overwrite=True (otherwise a numeric suffix is added). Returns {path, relative_path, size_bytes}. Next: run it
    with `npx playwright test <path>`.
    """
    client = get_client()
    cwd = Path(os.getcwd()).resolve()
    folder = (cwd / dest_dir).resolve()
    if not folder.is_relative_to(cwd):
        raise KawachError("dest_dir must stay inside the current working directory.")
    raw = await find_raw_bug(client, bug_id, run_id)
    script = await _script_text(client, raw)
    if not script:
        raise KawachError(f"No repro script is available for bug {bug_id} in run {run_id}.")
    name = sanitize_filename(filename) if filename else f"{sanitize_filename(bug_id)}-{_slug(raw.get('title') or '')}.spec.ts"
    if not name.endswith(".ts"):
        name += ".spec.ts"
    target = (folder / name).resolve()
    if not target.is_relative_to(cwd):
        raise KawachError("Refusing to write outside the current working directory.")
    folder.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        base = name[: -len(".spec.ts")] if name.endswith(".spec.ts") else name[: -len(".ts")]
        suffix = name[len(base):]
        n = 1
        while target.exists():  # never overwrite: name_1.spec.ts, name_2.spec.ts, ...
            target = (folder / f"{base}_{n}{suffix}").resolve()
            n += 1
    target.write_text(script, encoding="utf-8", newline="")
    rel = target.relative_to(cwd).as_posix()
    out = {"path": str(target), "relative_path": rel, "size_bytes": target.stat().st_size,
           "next_step_hint": hint(f"Run it with: npx playwright test {rel}")}
    if "apps/runner/fixtures" in script:
        out["note"] = ("The script imports its fixtures from '../../../apps/runner/fixtures' (the KAWACH runner). "
                       "Adjust that import to your own Playwright setup (base URL, credentials) before running it.")
    return out


# ---------------------------------------------------------------- pipeline

def _clamp_wait(seconds: int) -> int:
    return max(1, min(int(seconds), 600))


async def _finish(ctx: Any, run_id: str, wait_seconds: int, started: Optional[dict] = None) -> dict:
    """Wait up to wait_seconds, then return the digest plus pipeline status fields."""
    w = await wait_core(run_id, ctx, _WAIT_STAGES, _clamp_wait(wait_seconds), 3)
    summary = await digest(run_id)
    stage = summary["stage"]
    out: dict = {"run_id": run_id, "stage": stage, "still_running": bool(w.get("still_running")),
                 "summary": summary, "elapsed_seconds": w.get("elapsed_seconds")}
    if started:
        out["started"] = started
    if out["still_running"]:
        out["next_step_hint"] = hint(f"Still running. Call wait_for_run(run_id='{run_id}') again, then get_run_summary.")
    elif stage == "awaiting_review":
        n = (w.get("catalog_counts") or {}).get("by_status", {}).get("proposed", 0)
        total = (w.get("catalog_counts") or {}).get("total", 0)
        out["awaiting_review"] = {"tests_total": total, "tests_awaiting_review": n}
        out["message"] = (f"Manual mode: the run STOPPED at awaiting_review. {n} of {total} test(s) await your review; "
                          "nothing has been executed yet.")
        out["next_step_hint"] = hint("Call get_catalog, then review_tests or approve_all_and_resume (approving starts execution).")
    else:
        out["next_step_hint"] = hint(summary["recommended_next_action"])
    return out


@tool(WRITE)
async def run_qa_pipeline(
    ctx: Context,
    target_url: Annotated[Optional[str], Field(description="App URL to test; optional if project_id is given")] = None,
    project_id: Annotated[Optional[str], Field(description="Project to run against")] = None,
    spec_file_path: Annotated[Optional[str], Field(description="Local spec file to upload first")] = None,
    prompt: Annotated[Optional[str], Field(description="Natural-language testing focus")] = None,
    review_mode: Annotated[str, Field(description="manual (stops at awaiting_review) or autonomous")] = "manual",
    budgets: Annotated[Optional[dict], Field(description="Optional budgets, see get_defaults")] = None,
    username: Annotated[Optional[str], Field(description="Login username for the app under test")] = None,
    password: Annotated[Optional[str], Field(description="Login password for the app under test")] = None,
    wait_seconds: Annotated[int, Field(ge=1, le=600, description="How long to wait before returning (max 600)")] = 100,
) -> dict:
    """Run the whole QA flow in one call: health check, target check, optional spec upload, start, wait, summary.

    Aborts with a clear message if the backend is unreachable or the target is not allowed. In manual mode it
    stops at awaiting_review and says how many tests await review (approving them starts execution). If the run
    is still going after wait_seconds it returns still_running=true: call wait_for_run, then get_run_summary.
    """
    health = await system_tools.health_check()
    if health["status"] == "unreachable":
        raise KawachError(health["message"])
    if target_url:
        chk = await run_target_check(get_client(), target_url)
        if not chk["allowed"]:
            raise KawachError(f"Target not allowed: {chk['verdict']}. {chk.get('reason') or ''}".strip())
    started = await runs_tools.start_run(target_url=target_url, project_id=project_id, review_mode=review_mode, prompt=prompt,
                                         spec_file_path=spec_file_path, budgets=budgets, username=username, password=password)
    return await _finish(ctx, started["run_id"], wait_seconds, {k: started.get(k) for k in ("run_id", "mode", "target_url", "target_check")})


# ---------------------------------------------------------------- compare / retest

def _norm_title(t: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (t or "").lower().strip())


async def compare(run_a: str, run_b: str) -> dict:
    client = get_client()
    rows_a, rows_b = await load_bugs(client, run_a), await load_bugs(client, run_b)
    conf_a = [r for r in rows_a if r["status"] == "confirmed"]
    conf_b = [r for r in rows_b if r["status"] == "confirmed"]
    key = lambda r: (r.get("testId") or "", _norm_title(r["title"]))  # noqa: E731
    title_only = False

    def find(row: dict, pool: list[dict]) -> Optional[dict]:
        nonlocal title_only
        for c in pool:
            if key(c) == key(row):
                return c
        for c in pool:  # test ids can differ between runs: fall back to the title alone
            if _norm_title(c["title"]) == _norm_title(row["title"]):
                title_only = True
                return c
        return None

    fixed, persisting = [], []
    matched_b: set = set()
    for a in conf_a:
        hit = find(a, conf_b)
        if hit:
            persisting.append({**_short(a), "run_b_id": hit["id"]})
            matched_b.add(hit["id"])
        else:
            now = find(a, rows_b)
            fixed.append({**_short(a), "now": (now or {}).get("status", "absent")})
    new = []
    for b in conf_b:
        if b["id"] in matched_b:
            continue
        before = find(b, rows_a)
        new.append({**_short(b), "before": (before or {}).get("status", "absent")})
    flaky_b = [_short(r) for r in rows_b if r["status"] == "flaky"]
    ma, mb = await _metrics(run_a), await _metrics(run_b)
    rate = lambda m: ((m or {}).get("tests") or {}).get("pass_rate_percent")  # noqa: E731
    ra, rb = rate(ma), rate(mb)
    verdict = f"{len(fixed)} fixed, {len(new)} new, {len(persisting)} persisting"
    if flaky_b:
        verdict += f" ({len(flaky_b)} flaky candidate(s) in the new run are not counted)"
    out = {
        "run_a": run_a, "run_b": run_b, "fixed": fixed, "new": new, "persisting": persisting, "still_flaky": flaky_b,
        "verdict": verdict,
        "metrics_delta": {"pass_rate_percent": {"before": ra, "after": rb,
                                                 "change": round(rb - ra, 1) if ra is not None and rb is not None else None},
                          "confirmed_bugs": {"before": len(conf_a), "after": len(conf_b)}},
        "note": "Only confirmed (3/3) bugs count as fixed, new or persisting; flaky ones are listed separately.",
    }
    if title_only:
        out["matching_note"] = "Some bugs were matched by title only because their test ids differ between the runs."
    out["next_step_hint"] = hint("Fix the persisting bugs with get_bug_fix_context." if persisting
                                 else "All previously confirmed bugs are gone." if fixed else "No confirmed bugs in either run.")
    return out


@tool(READ)
async def compare_runs(
    run_a: Annotated[str, Field(description="Earlier run (before the fix)")],
    run_b: Annotated[str, Field(description="Later run (after the fix)")],
) -> dict:
    """Diff the verified bugs of two runs: which were fixed, which are new, which persist.

    Bugs are matched by (test id, normalised title), falling back to title alone (noted in matching_note). ONLY
    confirmed (3/3) bugs count toward fixed/new/persisting; flaky ones appear in still_flaky. Returns
    {fixed, new, persisting, still_flaky, verdict, metrics_delta}.
    """
    return await compare(run_a, run_b)


@tool(WRITE)
async def retest_after_fix(
    ctx: Context,
    previous_run_id: Annotated[str, Field(description="The run whose bugs you just fixed")],
    review_mode: Annotated[str, Field(description="autonomous (default, no human step) or manual")] = "autonomous",
    wait_seconds: Annotated[int, Field(ge=1, le=600)] = 100,
    spec_file_path: Annotated[Optional[str], Field(description="Spec to use again (the API cannot return the old run's spec)")] = None,
    spec_id: Annotated[Optional[str], Field(description="Id from upload_spec")] = None,
    allow_default_spec: Annotated[bool, Field(description="Proceed without a spec even though the previous run used one (backend default spec)")] = False,
    username: Annotated[Optional[str], Field(description="App login username, if the app needs one")] = None,
    password: Annotated[Optional[str], Field(description="App login password, if the app needs one")] = None,
) -> dict:
    """Re-run QA against the same target after a fix and compare with the previous run.

    Recovers target URL, project and page budget from the previous run. The spec text and app credentials cannot
    be read back from the API, so if the previous run used a spec you must pass spec_file_path/spec_id (or
    allow_default_spec=True); the tool says exactly what is missing and never guesses. If the new run is still going
    it returns {still_running, new_run_id}; call wait_for_run then compare_runs. When done it includes the comparison.
    """
    client = get_client()
    prev = await client.get(f"/runs/{previous_run_id}")
    target = prev.get("targetUrl") or prev.get("target_url")
    project_id = prev.get("projectId") or prev.get("project_id")
    if not target:
        raise KawachError("Cannot recover the target URL from the previous run. Call start_run with target_url instead.")
    catalog_rows = await client.get(f"/runs/{previous_run_id}/catalog") or []
    used_spec = any(t.get("spec_item_ids") for t in catalog_rows)
    if used_spec and not (spec_file_path or spec_id or allow_default_spec):
        raise KawachError(
            f"Run {previous_run_id} was planned from a spec, but the API cannot return it, so the retest cannot reuse it. "
            "Pass spec_file_path (path to your spec file) or spec_id, or pass allow_default_spec=True to use the backend's "
            "default spec. Nothing was started.")
    max_pages = (prev.get("budgets") or {}).get("max_pages")
    started = await runs_tools.start_run(
        target_url=target, project_id=project_id, review_mode=review_mode, prompt=prev.get("prompt") or None,
        spec_id=spec_id, spec_file_path=spec_file_path, budgets={"max_pages": max_pages} if max_pages else None,
        username=username, password=password)
    new_id = started["run_id"]
    out = await _finish(ctx, new_id, wait_seconds, {"new_run_id": new_id, "previous_run_id": previous_run_id, "mode": started.get("mode")})
    out["new_run_id"], out["previous_run_id"] = new_id, previous_run_id
    if out["still_running"]:
        out["next_step_hint"] = hint(f"wait_for_run('{new_id}'), then compare_runs('{previous_run_id}', '{new_id}')")
    elif out["stage"] == "done":
        out["comparison"] = await compare(previous_run_id, new_id)
        out["next_step_hint"] = hint(out["comparison"]["verdict"])
    return out


@tool(WRITE)
async def run_project_regression(
    ctx: Context,
    project_id: Annotated[str, Field(description="Project whose saved regression tests should run")],
    wait_seconds: Annotated[int, Field(ge=1, le=600)] = 100,
) -> dict:
    """Run a project's saved regression tests, wait, and return the same digest as get_run_summary plus failures.

    Wraps POST /projects/{id}/saved-tests/run-all (see run_saved_tests). Save tests first with
    save_test_to_project. Returns {run_id, stage, still_running, summary, failures[{test, error}]}.
    """
    started = await projects_tools.run_saved_tests(project_id)
    run_id = started.get("run_id")
    if not run_id:
        raise KawachError(f"The backend did not return a run id for the regression run (response: {trim(str(started.get('result')), 200)}).")
    out = await _finish(ctx, run_id, wait_seconds, {"run_id": run_id})
    if not out["still_running"]:
        try:
            tests = await get_client().get(f"/runs/{run_id}/tests") or []
            out["failures"] = [{"test": f"{t.get('id')}: {t.get('title')}", "error": trim(t.get("error_message"), 300)}
                               for t in tests if t.get("status") == "failed"][:20]
        except KawachError as e:
            if e.kind in ("unreachable", "timeout"):
                raise
    return out
