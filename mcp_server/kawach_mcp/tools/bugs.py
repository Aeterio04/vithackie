"""Bug list/detail tools and artifact download. A bug is confirmed only with 3 of 3 reproductions."""

import asyncio
import json
import re
from typing import Annotated, Optional
from urllib.parse import urlparse

from pydantic import Field

from ..client import get_client
from ..errors import KawachError
from ..fsafe import safe_dest, sanitize_filename
from ..formatting import fmt_verification, hint, listing, trim
from . import READ, WRITE, tool

RID = Annotated[str, Field(description="Run id, from list_runs or start_run")]
STATUS_ORDER = {"confirmed": 0, "flaky": 1, "not_reproduced": 2}
CODE_LIMIT = 6000
SEVERITIES = ("critical", "high", "medium", "low")


async def fetch_verification(client, run_id: str, bug_id: str) -> Optional[dict]:
    """The real 3x verification record. The bug API fabricates placeholder replays when it cannot parse this
    file, so the raw file (served by the run-files route) is the only trustworthy source."""
    try:
        return json.loads(await client.get_text(f"/runs/{run_id}/files/verification/{bug_id}.json"))
    except KawachError as e:
        if e.kind in ("unreachable", "timeout"):
            raise
        return None
    except ValueError:
        return None


def replays_from_verification(ver: Optional[dict]) -> list[dict]:
    attempts = (ver or {}).get("attempts") if isinstance(ver, dict) else None
    out = []
    for i, a in enumerate(attempts or [], 1):
        if not isinstance(a, dict) or "reproduced" not in a:
            continue
        out.append({"index": a.get("attempt", i), "result": "reproduced" if a.get("reproduced") else "not_reproduced",
                    "outcome": a.get("outcome"), "duration_ms": a.get("durationMs")})
    return out


def verdict_from_replays(replays: list[dict], backend_status: Optional[str]) -> tuple[str, Optional[str]]:
    """Return (status, note). Confirmed needs 3 finished real replays all reproduced; fewer than 3 = unverified."""
    done = [r for r in replays if r.get("result") in ("reproduced", "not_reproduced")]
    if len(done) >= 3:
        hits = sum(1 for r in done[:3] if r["result"] == "reproduced")
        derived = "confirmed" if hits == 3 else ("flaky" if hits else "not_reproduced")
        note = None
        if backend_status in STATUS_ORDER and backend_status != derived:
            note = f"Backend labelled this '{backend_status}' but the replays show {hits}/3, so it is treated as {derived}."
        return derived, note
    note = "No real verification record with 3 finished replays was found, so this is NOT counted as confirmed."
    if backend_status:
        note += f" (backend label: {backend_status})"
    return "unverified", note


def _test_id(bug: dict) -> Optional[str]:
    m = re.search(r"/scripts/(.+?)\.spec\.ts", bug.get("repro_script_url") or "")
    return m.group(1) if m else None


def norm_bug(b: dict, ver: Optional[dict] = None) -> dict:
    """Normalise a backend bug. `replays` come ONLY from the real verification record (`ver`)."""
    replays = replays_from_verification(ver)
    status, note = verdict_from_replays(replays, b.get("status"))
    finished = len(replays) >= 3 and all(r.get("result") in ("reproduced", "not_reproduced") for r in replays)
    verification = (fmt_verification([{"reproduced": r.get("result") == "reproduced"} for r in replays])
                    if finished else "not verified yet")
    row = {
        "id": b.get("id"), "testId": _test_id(b), "title": b.get("title"), "severity": b.get("severity"),
        "status": status, "category": b.get("category"), "verification": verification,
        "specRef": b.get("spec_item_ids") or [],
    }
    row["backend_status"] = b.get("status")
    row["replays"] = replays
    if note:
        row["status_note"] = note
    return row


async def find_raw_bug(client, bug_id: str, run_id: Optional[str] = None) -> dict:
    """One raw backend bug. With run_id the lookup is scoped to that run (the global /bugs/{id} route returns the
    first run that has a bug with that id, which is the wrong run when ids repeat)."""
    if run_id:
        for b in await client.get(f"/runs/{run_id}/bugs") or []:
            if b.get("id") == bug_id:
                return {**b, "run_id": b.get("run_id") or run_id}
        raise KawachError(f"Bug {bug_id} not found in run {run_id}.", 404)
    return await client.get(f"/bugs/{bug_id}")


async def load_bugs(client, run_id: str) -> list[dict]:
    """All bugs of a run as normalised rows, each verified against its real verification record."""
    raw = await client.get(f"/runs/{run_id}/bugs") or []
    sem = asyncio.Semaphore(5)

    async def one(b: dict) -> dict:
        async with sem:
            return norm_bug(b, await fetch_verification(client, run_id, b.get("id")))

    return list(await asyncio.gather(*[one(b) for b in raw]))


def _strip(row: dict) -> dict:
    """Public list-row shape (replays are shown only on the full bug card)."""
    return {k: v for k, v in row.items() if k != "replays"}


@tool(READ)
async def list_bugs(
    run_id: RID,
    status: Annotated[Optional[str], Field(description="confirmed, flaky or not_reproduced")] = None,
    severity: Annotated[Optional[str], Field(description="critical, high, medium or low")] = None,
) -> dict:
    """List defects found in a run, with the verification evidence next to each one.

    A bug is CONFIRMED only when 3 of 3 replays reproduce it; 1/3 or 2/3 is FLAKY; 0/3 is NOT REPRODUCED.
    The status is re-derived from the replays, never copied blindly. Rows are ordered confirmed, flaky,
    not_reproduced. Returns {bugs, summary{confirmed, flaky, not_reproduced, total}, by_severity (confirmed
    only), honesty_note}. summary.total excludes not_reproduced. Next: get_bug for the full card.
    """
    if status is not None and status not in ("confirmed", "flaky", "not_reproduced"):
        raise KawachError("Invalid status: must be confirmed, flaky or not_reproduced.")
    if severity is not None and severity not in SEVERITIES:
        raise KawachError(f"Invalid severity {severity!r}: must be one of {', '.join(SEVERITIES)}.")
    rows = await load_bugs(get_client(), run_id)
    n = lambda s: sum(1 for r in rows if r["status"] == s)  # noqa: E731
    confirmed, flaky, nr = n("confirmed"), n("flaky"), n("not_reproduced")
    other = len(rows) - confirmed - flaky - nr
    by_sev: dict = {}
    for r in rows:
        if r["status"] == "confirmed":
            by_sev[r["severity"]] = by_sev.get(r["severity"], 0) + 1
    shown = [r for r in rows if (not status or r["status"] == status) and (not severity or r["severity"] == severity)]
    shown.sort(key=lambda r: STATUS_ORDER.get(r["status"], 3))
    out = listing("bugs", [_strip(r) for r in shown], 50, summary={
        "confirmed": confirmed, "flaky": flaky, "not_reproduced": nr, "unverified": other,
        "total": confirmed + flaky + other}, by_severity=by_sev)
    notes = []
    if flaky:
        notes.append(f"{flaky} flaky candidate(s) are intermittent (1/3 or 2/3 replays) and are NOT counted as confirmed defects.")
    if nr:
        notes.append(f"{nr} candidate(s) did not reproduce (0/3) and are excluded from the bug total.")
    if other:
        notes.append(f"{other} candidate(s) are not fully verified yet and are NOT confirmed.")
    if notes:
        out["honesty_note"] = " ".join(notes)
    out["next_step_hint"] = hint("Call get_bug with a bug id for steps, evidence and the verification timeline."
                                 if rows else "No bugs recorded for this run.")
    return out


@tool(READ)
async def get_bug(
    bug_id: Annotated[str, Field(description="Bug id from list_bugs")],
    run_id: Annotated[Optional[str], Field(description="Run the bug belongs to. Strongly recommended: ids like B01 exist in every run")] = None,
) -> dict:
    """Get the full bug card: steps, expected vs actual, evidence links and the 3-replay verification timeline.

    Pass run_id so the right run's bug is used. Evidence URLs are absolute (download with download_artifact). Never includes binary data. The Playwright
    reproduction script is included up to 6,000 characters (a full copy can be saved with save_repro_script
    in a later release). Next: fix the code, then retest.
    """
    client = get_client()
    b = await find_raw_bug(client, bug_id, run_id)
    ver = await fetch_verification(client, b.get("run_id") or run_id or "", bug_id)
    full = norm_bug(b, ver)
    replays, row = full["replays"], _strip(full)
    timeline = []
    for r in replays:
        res = str(r.get("result") or "unknown").replace("_", " ")
        outcome = f" ({r['outcome']})" if r.get("outcome") else ""
        dur = f" {r['duration_ms']}ms" if r.get("duration_ms") is not None else ""
        timeline.append(f"Trial {r.get('index')}: {res}{outcome}{dur}")
    hits = sum(1 for r in replays if r.get("result") == "reproduced")
    label = {"confirmed": "CONFIRMED", "flaky": "FLAKY (intermittent, not a confirmed defect)",
             "not_reproduced": "NOT REPRODUCED", "unverified": "UNVERIFIED (not a confirmed defect)"}.get(row["status"], row["status"].upper())
    timeline.append(f"Verdict: {label}" + (f" ({hits}/{len(replays)} reproduced)" if replays else ""))
    ev = b.get("evidence") or {}
    code = None
    script_url = b.get("repro_script_url")
    if script_url:
        try:
            code = await client.get_text(script_url)
        except KawachError as e:
            if e.kind == "unreachable":
                raise
    out = {
        **row, "run_id": b.get("run_id"),
        "steps_to_reproduce": b.get("steps_to_reproduce") or [],
        "expected_result": b.get("expected"), "actual_result": b.get("actual"),
        "console_errors": ev.get("console") or [],
        "playwright_code": trim(code, CODE_LIMIT) if code else None,
        "evidence": {
            "screenshots": [client.absolute_url(u) for u in ev.get("screenshots") or []],
            "video_url": client.absolute_url(ev.get("video_url")),
            "trace_url": client.absolute_url(ev.get("trace_url")),
            "repro_script_url": client.absolute_url(script_url),
        },
        "verification_timeline": timeline,
    }
    if code and len(code) > CODE_LIMIT:
        out["code_note"] = "Script truncated; the full copy is available at evidence.repro_script_url."
    return out


@tool(WRITE)
async def download_artifact(
    artifact_id_or_url: Annotated[str, Field(description="Artifact id, or a backend file URL/path from get_bug evidence")],
    filename: Annotated[Optional[str], Field(description="Optional name to save as (sanitized)")] = None,
) -> dict:
    """Download an artifact (screenshot, video, trace, script) from the backend to the local download folder.

    Saves under KAWACH_DOWNLOAD_DIR/artifacts/, never overwriting. Returns {path, size_bytes, content_type}.
    Only the configured backend host is allowed.
    """
    client = get_client()
    ref = artifact_id_or_url.strip()
    if not ref:
        raise KawachError("artifact_id_or_url must not be empty.")
    if ref.startswith(("http://", "https://")):
        if urlparse(ref).netloc != urlparse(client.base_url).netloc:
            raise KawachError("Refusing to download from a host other than the configured backend.")
        path = ref
        default_name = urlparse(ref).path.rsplit("/", 1)[-1]
    elif ref.startswith("/"):
        path = ref
        default_name = ref.rsplit("/", 1)[-1]
    else:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", ref):
            raise KawachError("Invalid artifact id.")
        path = f"/artifacts/{ref}"
        default_name = ref
    base = client.settings.download_dir.resolve()
    dest = safe_dest(base, "artifacts", filename=sanitize_filename(filename or default_name, "artifact"))
    saved, size, ctype = await client.download(path, dest)
    return {"path": str(saved), "size_bytes": size, "content_type": ctype}
