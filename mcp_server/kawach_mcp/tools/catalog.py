"""Test catalog and review-gate tools."""

from typing import Annotated, Optional

from pydantic import Field

from ..client import get_client
from ..errors import KawachError
from ..formatting import STAGE_MEANING, hint, listing
from . import READ, WRITE, tool

RID = Annotated[str, Field(description="Run id, from list_runs or start_run")]
STATUSES = ("proposed", "approved", "rejected")
PRIORITIES = ("critical", "high", "medium", "low")
_BACKEND_STATUS = {"pending": "proposed", "proposed": "proposed", "approved": "approved", "rejected": "rejected"}
MAX_STEP_TESTS = 25


def norm_test(t: dict, with_steps: bool = False) -> dict:
    steps = t.get("steps") or []
    out = {
        "id": t.get("id"),
        "title": t.get("title"),
        "category": t.get("category"),          # not provided by the backend (always null today)
        "priority": t.get("priority"),
        "status": _BACKEND_STATUS.get(t.get("review_status") or t.get("status"), t.get("review_status")),
        "specRef": t.get("spec_item_ids") or [],
        "pagePath": t.get("page_path"),         # not provided by the backend (always null today)
        "step_count": len(steps),
        "source": t.get("source"),
    }
    if with_steps:
        out["steps"] = steps
        out["expected_result"] = t.get("expected_result")
    return out


async def fetch_catalog(run_id: str) -> list[dict]:
    return await get_client().get(f"/runs/{run_id}/catalog") or []


async def require_review_open(run_id: str) -> dict:
    """Review actions are only valid in 'awaiting_review'. Returns the run, else raises a helpful error."""
    run = await get_client().get(f"/runs/{run_id}")
    stage = run.get("stage")
    if stage == "awaiting_review":
        return run
    if (run.get("review_mode") or run.get("mode")) == "autonomous":
        raise KawachError(f"Run {run_id} is in autonomous mode (stage '{stage}'); the reviewer agent decides which "
                          "tests run, so there is no human review gate. Read-only tools like get_catalog still work.")
    raise KawachError(f"Run {run_id} is in stage '{stage}'; the review gate is only open in 'awaiting_review'. "
                      "Use wait_for_run to wait for it.")


def _unknown_ids(unknown: list[str], valid: list[str]) -> KawachError:
    shown = ", ".join(valid[:30]) + (" ..." if len(valid) > 30 else "")
    return KawachError(f"Unknown test id(s): {', '.join(unknown)}. Valid ids: {shown or '(catalog is empty)'}.")


def _counts(tests: list[dict]) -> dict:
    by_status: dict = {}
    by_priority: dict = {}
    for t in tests:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
        by_priority[t["priority"]] = by_priority.get(t["priority"], 0) + 1
    return {"by_status": by_status, "by_priority": by_priority}


@tool(READ)
async def get_catalog(
    run_id: RID,
    status: Annotated[Optional[str], Field(description="Only tests with this status: proposed, approved, rejected")] = None,
    priority: Annotated[Optional[str], Field(description="Only this priority: critical, high, medium, low")] = None,
    category: Annotated[Optional[str], Field(description="Only this category (the backend does not report categories yet)")] = None,
    include_steps: Annotated[bool, Field(description="Include steps and expected results (first 25 tests only)")] = False,
) -> dict:
    """Show the test catalog the planner proposed for a run (works in any stage).

    Returns compact tests {id, title, category, priority, status, specRef, pagePath, step_count}, plus
    counts by status/priority and spec_coverage. Statuses: proposed (awaiting decision), approved, rejected.
    Next: review_tests / approve_all_and_resume while the run is awaiting_review.
    """
    if status is not None and status not in STATUSES:
        raise KawachError(f"Invalid status {status!r}: must be one of {', '.join(STATUSES)}.")
    if priority is not None and priority not in PRIORITIES:
        raise KawachError(f"Invalid priority {priority!r}: must be one of {', '.join(PRIORITIES)}.")
    client = get_client()
    raw = await fetch_catalog(run_id)
    if not raw:
        run = await client.get(f"/runs/{run_id}")
        stage = run.get("stage")
        return {"tests": [], "count": 0, "stage": stage,
                "message": f"The catalog is not generated yet (run is '{stage}': {STAGE_MEANING.get(stage, '')}). "
                           "It appears when planning finishes, at stage 'awaiting_review' (manual mode).",
                "next_step_hint": hint("Call wait_for_run to wait for awaiting_review.")}
    tests = [norm_test(t) for t in raw]
    counts = _counts(tests)
    refs = sorted({r for t in tests for r in t["specRef"]})
    notes = []
    if category and not any(t["category"] for t in tests):
        notes.append("The backend does not report test categories, so the category filter was ignored.")
    shown = [t for t in tests if (not status or t["status"] == status) and (not priority or t["priority"] == priority)
             and (not category or not any(x["category"] for x in tests) or t["category"] == category)]
    if include_steps:
        by_id = {t["id"]: t for t in raw}
        for t in shown[:MAX_STEP_TESTS]:
            t.update(steps=by_id[t["id"]].get("steps") or [], expected_result=by_id[t["id"]].get("expected_result"))
        if len(shown) > MAX_STEP_TESTS:
            notes.append(f"Steps are included for the first {MAX_STEP_TESTS} of {len(shown)} tests only; use get_test for others.")
    out = listing("tests", shown, 50, counts=counts, spec_coverage={"spec_refs": refs, "count": len(refs)})
    if notes:
        out["notes"] = notes
    pending = counts["by_status"].get("proposed", 0)
    out["next_step_hint"] = hint(f"{pending} test(s) await a decision: use review_tests or approve_all_and_resume."
                                 if pending else "No tests are awaiting a decision.")
    return out


@tool(READ)
async def get_test(run_id: RID, test_id: Annotated[str, Field(description="Test id, e.g. T01")]) -> dict:
    """Get one catalog test with its full steps and expected result."""
    raw = await fetch_catalog(run_id)
    for t in raw:
        if t.get("id") == test_id:
            return norm_test(t, with_steps=True)
    raise _unknown_ids([test_id], [t.get("id") for t in raw])


@tool(WRITE)
async def update_test(
    run_id: RID,
    test_id: Annotated[str, Field(description="Test id, e.g. T01")],
    status: Annotated[Optional[str], Field(description="approved or rejected (proposed cannot be restored). Approving starts execution")] = None,
    priority: Annotated[Optional[str], Field(description="critical, high, medium or low")] = None,
    title: Optional[str] = None,
    description: Annotated[Optional[str], Field(description="The expected result text")] = None,
    steps: Annotated[Optional[list[str]], Field(description="Replacement step list, plain-language strings")] = None,
    reason: Annotated[Optional[str], Field(description="Required when status=rejected")] = None,
) -> dict:
    """Edit one catalog test: its priority, title, expected result, steps, or its review status.

    Field edits use the catalog PATCH route. A status change goes through the review route (only valid in
    awaiting_review); NOTE the backend starts executing as soon as any test is approved. Rejecting needs a
    reason. At least one field is required. Returns the updated test.
    """
    if all(v is None for v in (status, priority, title, description, steps)):
        raise KawachError("Nothing to update: pass at least one of status, priority, title, description, steps.")
    if status is not None and status not in STATUSES:
        raise KawachError(f"Invalid status {status!r}: must be one of {', '.join(STATUSES)}.")
    if priority is not None and priority not in PRIORITIES:
        raise KawachError(f"Invalid priority {priority!r}: must be one of {', '.join(PRIORITIES)}.")
    if steps is not None and (not steps or any(not str(s).strip() for s in steps)):
        raise KawachError("steps must be a non-empty list of non-empty strings.")
    if status == "rejected" and not (reason or "").strip():
        raise KawachError("A reason is required when rejecting a test.")
    client = get_client()
    current = next((t for t in await fetch_catalog(run_id) if t.get("id") == test_id), None)
    if current is None:
        raise _unknown_ids([test_id], [t.get("id") for t in await fetch_catalog(run_id)])
    cur_status = norm_test(current)["status"]
    if status == "proposed" and cur_status != "proposed":
        raise KawachError(f"Test {test_id} is already {cur_status}; the backend cannot move a test back to proposed.")
    if status and status != cur_status:
        await require_review_open(run_id)
    body = {k: v for k, v in {"title": title, "expected_result": description, "steps": steps,
                              "priority": priority}.items() if v is not None}
    result = None
    if body:
        result = await client.patch(f"/runs/{run_id}/catalog/{test_id}", body)
    changed_status = False
    if status and status != "proposed" and status != cur_status:
        await _send_review(run_id, [test_id], "approved" if status == "approved" else "rejected",
                           (reason or "Approved via MCP").strip())
        changed_status = True
    updated = next((t for t in await fetch_catalog(run_id) if t.get("id") == test_id), result or current)
    out = {"test": norm_test(updated, with_steps=True)}
    if status and not changed_status:
        out["unchanged"] = f"Status was already {cur_status}."
    return out


@tool(WRITE)
async def add_test(
    run_id: RID,
    title: str,
    category: Annotated[str, Field(description="e.g. functional, security, validation, ui")],
    priority: Annotated[str, Field(description="critical, high, medium or low")],
    page_path: Annotated[str, Field(description="Page the test targets, e.g. /login")],
    steps: Annotated[list[dict], Field(description="At least 2 steps: [{\"action\": \"...\", \"expected\": \"...\"}]")],
    spec_ref: Annotated[Optional[str], Field(description="Spec item this test covers, e.g. S3")] = None,
) -> dict:
    """Ask the planner to add a custom test to the catalog (only while awaiting_review).

    The backend generates the final test from a prompt, so your steps guide it rather than being copied
    verbatim. Returns the generated test id. New tests start as proposed.
    """
    if not title.strip() or not page_path.strip() or not category.strip():
        raise KawachError("title, category and page_path must not be empty.")
    if priority not in PRIORITIES:
        raise KawachError(f"Invalid priority {priority!r}: must be one of {', '.join(PRIORITIES)}.")
    if len(steps) < 2:
        raise KawachError("A test needs at least 2 steps.")
    numbered = []
    for n, s in enumerate(steps, 1):
        action = str((s or {}).get("action", "")).strip()
        if not action:
            raise KawachError(f"Step {n} has an empty action.")
        exp = str(s.get("expected") or "").strip()
        numbered.append(f"{n}. {action}" + (f" -> expect: {exp}" if exp else ""))
    await require_review_open(run_id)
    prompt = (f"Add a {priority}-priority {category} test titled '{title.strip()}' for page {page_path.strip()}"
              + (f", covering spec item {spec_ref}" if spec_ref else "") + ". Steps:\n" + "\n".join(numbered))
    created = await get_client().post(f"/runs/{run_id}/catalog/test", {"prompt": prompt})
    return {"test_id": created.get("id"), "test": norm_test(created, with_steps=True),
            "next_step_hint": hint("New tests start as proposed; approve it with review_tests or update_test.")}


def _decision_value(d) -> str:
    v = str(d or "").lower()
    return {"approve": "approved", "approved": "approved", "reject": "rejected", "rejected": "rejected"}.get(v, "")


REVIEW_TIMEOUT = 25.0  # the backend executes the pipeline inside the review request; do not wait for all of it


async def _send_review(run_id: str, ids: list[str], decision: str, reason: str) -> dict:
    """POST one review decision. A read timeout is not a failure: the backend keeps executing after the
    client stops waiting, so report it as submitted and let the caller read the stage."""
    try:
        res = await get_client().request("POST", f"/runs/{run_id}/review", timeout=REVIEW_TIMEOUT,
                                         json_body={"test_ids": ids, "decision": decision, "reason": reason})
        return {"timed_out": False, **(res if isinstance(res, dict) else {})}
    except KawachError as e:
        if e.kind == "timeout":
            return {"timed_out": True}
        raise


@tool(WRITE)
async def review_tests(
    run_id: RID,
    decisions: Annotated[list[dict], Field(description="[{\"test_id\": \"T01\", \"decision\": \"approve\"|\"reject\", \"reason\": \"...\"}]; reason required for rejects")],
    resume: Annotated[bool, Field(description="Must be true to allow execution to start (backend auto-starts once any test is approved)")] = False,
) -> dict:
    """Approve or reject catalog tests at the review gate (run must be awaiting_review).

    Everything is validated before any call: known ids, no duplicates, reasons on rejects. IMPORTANT: the
    backend starts executing as soon as at least one test is approved after a review call, so if the result
    leaves any test approved you must pass resume=True to confirm. Tests already in the requested state are
    reported as unchanged. Rejections are sent first, approvals last. Returns
    {ok, decisions_count, approved, rejected, unchanged, stage}.
    """
    if not decisions:
        raise KawachError("decisions must not be empty.")
    parsed: dict = {}
    for d in decisions:
        tid = str((d or {}).get("test_id") or "").strip()
        dec = _decision_value((d or {}).get("decision"))
        if not tid or not dec:
            raise KawachError(f"Each decision needs test_id and decision 'approve' or 'reject' (got {d!r}).")
        if tid in parsed:
            raise KawachError(f"Duplicate decision for test {tid}.")
        reason = str(d.get("reason") or "").strip()
        if dec == "rejected" and not reason:
            raise KawachError(f"A reason is required to reject test {tid}.")
        parsed[tid] = (dec, reason or "Approved via MCP")
    await require_review_open(run_id)
    catalog = {t["id"]: norm_test(t) for t in await fetch_catalog(run_id)}
    unknown = [t for t in parsed if t not in catalog]
    if unknown:
        raise _unknown_ids(unknown, list(catalog))
    rejects, approves, unchanged = [], [], []
    for tid, (dec, reason) in parsed.items():
        want = "approved" if dec == "approved" else "rejected"
        if catalog[tid]["status"] == want:
            unchanged.append(tid)
        else:
            (approves if want == "approved" else rejects).append((tid, reason))
    final_approved = {t for t, v in catalog.items() if v["status"] == "approved"}
    final_approved |= {t for t, _ in approves}
    final_approved -= {t for t, _ in rejects}
    if resume and not final_approved:
        raise KawachError("resume=True but no test would be approved; an empty approved set cannot run. "
                          "Approve at least one test.")
    if not resume and final_approved:
        raise KawachError(f"{len(final_approved)} test(s) would be approved and the backend starts execution "
                          "immediately after a review call. Call again with resume=True to confirm, "
                          "or reject everything you do not want first.")
    stage, timed_out = None, False
    for decision, items in (("rejected", rejects), ("approved", approves)):
        if not items:
            continue
        reasons = {r for _, r in items}
        reason = reasons.pop() if len(reasons) == 1 else "; ".join(f"{t}: {r}" for t, r in items)
        sent = await _send_review(run_id, [t for t, _ in items], decision, reason)
        timed_out = timed_out or sent["timed_out"]
    if rejects or approves:
        stage = (await get_client().get(f"/runs/{run_id}")).get("stage")
    out = {"ok": True, "decisions_count": len(parsed), "approved": [t for t, _ in approves],
           "rejected": [t for t, _ in rejects], "unchanged": unchanged, "stage": stage,
           "next_step_hint": hint("Execution has started. Call wait_for_run to follow it." if final_approved
                                  else "Nothing is approved yet.")}
    if timed_out:
        out["note"] = ("The backend runs execution inside the review request, so the call timed out while it kept "
                       "running in the background. The decisions were submitted; follow progress with wait_for_run.")
    return out


@tool(WRITE)
async def approve_all_and_resume(
    run_id: RID,
    reason: Annotated[str, Field(description="Audit reason recorded with the decision")] = "Approved via MCP",
) -> dict:
    """Approve every proposed test in one review call and let execution start (run must be awaiting_review).

    Use when the user trusts the whole catalog. Rejected tests stay rejected. Returns
    {ok, approved, already_approved, stage}. Next: wait_for_run.
    """
    await require_review_open(run_id)
    catalog = [norm_test(t) for t in await fetch_catalog(run_id)]
    proposed = [t["id"] for t in catalog if t["status"] == "proposed"]
    already = [t["id"] for t in catalog if t["status"] == "approved"]
    if not proposed and not already:
        raise KawachError("The catalog has no proposed or approved tests, so there is nothing to run.")
    timed_out = False
    if proposed:
        timed_out = (await _send_review(run_id, proposed, "approved", reason))["timed_out"]
    stage = (await get_client().get(f"/runs/{run_id}")).get("stage")
    out = {"ok": True, "approved": proposed, "already_approved": already, "stage": stage,
           "next_step_hint": hint("Execution has started. Call wait_for_run to follow it.")}
    if timed_out:
        out["note"] = ("The backend runs execution inside the review request, so the call timed out while it kept "
                       "running in the background. The approval was submitted; follow progress with wait_for_run.")
    return out


@tool(WRITE)
async def reject_tests(
    run_id: RID,
    test_ids: Annotated[list[str], Field(description="Tests to reject")],
    reason: Annotated[str, Field(description="Why they are rejected (required)")],
) -> dict:
    """Reject catalog tests in one review call, without starting the run (run must be awaiting_review).

    Refuses if any other test is already approved, because the backend would then start executing
    immediately; use review_tests with resume=True in that case.
    """
    if not test_ids or not (reason or "").strip():
        raise KawachError("test_ids and a non-empty reason are required.")
    if len(set(test_ids)) != len(test_ids):
        raise KawachError("test_ids contains duplicates.")
    await require_review_open(run_id)
    catalog = {t["id"]: norm_test(t) for t in await fetch_catalog(run_id)}
    unknown = [t for t in test_ids if t not in catalog]
    if unknown:
        raise _unknown_ids(unknown, list(catalog))
    approved = [t for t, v in catalog.items() if v["status"] == "approved" and t not in test_ids]
    if approved:
        raise KawachError(f"{len(approved)} other test(s) are already approved, so the backend would start the run "
                          "right after this rejection. Use review_tests with resume=True if that is intended.")
    todo = [t for t in test_ids if catalog[t]["status"] != "rejected"]
    if todo:
        await _send_review(run_id, todo, "rejected", reason.strip())
    return {"ok": True, "rejected": todo, "unchanged": [t for t in test_ids if t not in todo],
            "next_step_hint": hint("Approve the remaining tests with review_tests or approve_all_and_resume.")}


@tool(READ)
async def get_review_log(run_id: RID) -> dict:
    """Show the audit trail of review decisions (who approved/rejected which test, and why)."""
    rows = await get_client().get(f"/runs/{run_id}/review-log") or []
    return listing("decisions", [{"test_id": r.get("test_id"), "decision": r.get("decision"),
                                  "actor": r.get("actor"), "reason": r.get("reason"), "at": r.get("at")}
                                 for r in rows])
