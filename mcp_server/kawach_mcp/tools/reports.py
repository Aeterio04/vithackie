"""Report, metrics and export tools. Everything written to disk goes through fsafe."""

import csv
import io
import json
from pathlib import Path
from typing import Annotated, Optional

from pydantic import Field

from ..client import get_client
from ..errors import KawachError
from ..formatting import hint, trim
from ..fsafe import plain_filename, safe_dest, safe_extract_zip, sanitize_filename
from . import READ, WRITE, tool
from .catalog import norm_test

RID = Annotated[str, Field(description="Run id, from list_runs or start_run")]


def _base() -> Path:
    return get_client().settings.download_dir.resolve()


def _trunc_report(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return (text[:max_chars] + f"\n\n[truncated {len(text) - max_chars} chars; "
            "use export_report_markdown for the full file]"), True


@tool(READ)
async def get_report(
    run_id: RID,
    max_chars: Annotated[int, Field(ge=500, le=20000, description="Max characters of report text to return")] = 12000,
) -> dict:
    """Read the run's markdown executive report (summary, bugs, coverage), truncated if long.

    Only meaningful once the run has reached reporting/done. Returns {report, truncated}. For the whole
    file call export_report_markdown. Next: list_bugs for evidence on each defect.
    """
    client = get_client()
    max_chars = max(500, min(int(max_chars), 20000))
    try:
        text = await client.get_text(f"/runs/{run_id}/files/report.md")
        body, cut = _trunc_report(text, max_chars)
        return {"format": "markdown", "report": body, "truncated": cut}
    except KawachError as e:
        if e.status_code != 404:
            raise
    data = await client.get(f"/runs/{run_id}/report")  # structured fallback when report.md is not written yet
    summary = {"run": {k: (data.get("run") or {}).get(k) for k in ("id", "stage", "target_url")},
               "summary_counts": data.get("summary_counts"),
               "verification_funnel": data.get("verification_funnel")}
    body, cut = _trunc_report(json.dumps(summary, indent=2), max_chars)
    return {"format": "json-summary", "report": body, "truncated": cut,
            "message": "report.md is not generated yet (run not finished); showing the structured summary instead."}


@tool(READ)
async def get_metrics(run_id: RID) -> dict:
    """Run metrics: wall clock, test totals, pass rate, bug funnel, coverage, LLM token usage and cost."""
    m = await get_client().get(f"/runs/{run_id}/metrics")
    t, b, c, llm = (m.get("tests") or {}), (m.get("bugs") or {}), (m.get("coverage") or {}), (m.get("llm") or {})
    ran = (t.get("passed") or 0) + (t.get("failed") or 0) + (t.get("errored") or 0)
    rate = round(100 * (t.get("passed") or 0) / ran, 1) if ran else None
    wall = m.get("wallClockSeconds")
    items = c.get("specItems") or 0
    cov = round(100 * (c.get("specItemsCovered") or 0) / items, 1) if items else None
    cost = llm.get("costUsd")
    summary = (f"{t.get('passed', 0)}/{ran} tests passed" + (f" ({rate}%)" if rate is not None else "")
               + f", {b.get('confirmed', 0)} confirmed bug(s), {b.get('flaky', 0)} flaky"
               + (f", took {round(wall)}s" if wall else "") + (f", LLM cost ${cost:.4f}" if cost is not None else "") + ".")
    return {
        "summary": summary, "wall_clock_seconds": wall,
        "tests": {"planned": t.get("planned"), "approved": t.get("approved"), "passed": t.get("passed"),
                  "failed": t.get("failed"), "errored": t.get("errored"), "pass_rate_percent": rate},
        "bugs": {"candidates": b.get("candidates"), "confirmed": b.get("confirmed"), "flaky": b.get("flaky"),
                 "not_reproduced": b.get("notReproduced")},
        "spec_coverage": {"covered": c.get("specItemsCovered"), "total": c.get("specItems"), "percent": cov},
        "coverage": {"pages": [c.get("pagesExercised"), c.get("pagesInMap")], "forms": [c.get("formsExercised"), c.get("formsInMap")]},
        "llm": {"calls": llm.get("calls"), "input_tokens": llm.get("inputTokens"),
                "output_tokens": llm.get("outputTokens"), "cost_usd": cost},
    }


async def _download(run_id: str, route: str, filename: str) -> dict:
    client = get_client()
    dest = safe_dest(_base(), run_id, filename=filename)
    path, size, ctype = await client.download(route, dest)
    return {"path": str(path), "size_bytes": size, "content_type": ctype}


@tool(WRITE)
async def export_run_archive(run_id: RID) -> dict:
    """Download the run's export zip to KAWACH_DOWNLOAD_DIR/<run_id>/run_<id>.zip.

    The backend's export route returns the passing tests as a runnable Playwright project, or the whole run
    folder (secrets excluded) when no test passed. Returns {path, size_bytes, content_type}.
    """
    res = await _download(run_id, f"/runs/{run_id}/export", f"run_{sanitize_filename(run_id)}.zip")
    res["note"] = "Contents: passing tests as a Playwright project, or the full run folder if nothing passed."
    return res


@tool(WRITE)
async def export_playwright_scripts(
    run_id: RID,
    extract_to: Annotated[Optional[str], Field(description="Optional sub-folder name under the download dir to extract into")] = None,
) -> dict:
    """Download the passing Playwright test scripts (a standalone project) as a zip, optionally extracting it.

    Extraction is zip-slip safe, capped at 200 MB and never overwrites files. Returns {path, size_bytes}
    plus {extracted_to, files} when extract_to is given.
    """
    res = await _download(run_id, f"/runs/{run_id}/export/scripts", f"{sanitize_filename(run_id)}_scripts.zip")
    if extract_to:
        dest = safe_dest(_base(), sanitize_filename(extract_to, "scripts"), filename="_probe")
        dest.parent.mkdir(parents=True, exist_ok=True)
        info = safe_extract_zip(Path(res["path"]), dest.parent)
        res.update(extracted_to=str(dest.parent), files=info["files"])
    return res


@tool(WRITE)
async def export_catalog(
    run_id: RID,
    format: Annotated[str, Field(description="json or csv")] = "json",
) -> dict:
    """Save the run's test catalog to disk as JSON or CSV and return the path.

    Built from the catalog API (the backend has no catalog export route).
    """
    if format not in ("json", "csv"):
        raise KawachError("format must be 'json' or 'csv'.")
    tests = [norm_test(t, with_steps=True) for t in await get_client().get(f"/runs/{run_id}/catalog") or []]
    if format == "json":
        data = json.dumps(tests, indent=2)
    else:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "title", "priority", "status", "spec_refs", "step_count", "expected_result"])
        for t in tests:
            w.writerow([t["id"], t["title"], t["priority"], t["status"], " ".join(t["specRef"]),
                        t["step_count"], t.get("expected_result")])
        data = buf.getvalue()
    dest = safe_dest(_base(), run_id, filename=f"catalog_{sanitize_filename(run_id)}.{format}")
    dest.write_text(data, encoding="utf-8", newline="")
    return {"path": str(dest), "size_bytes": dest.stat().st_size, "tests": len(tests)}


@tool(WRITE)
async def export_report_markdown(run_id: RID) -> dict:
    """Download the full markdown report (report.md) to KAWACH_DOWNLOAD_DIR/<run_id>/."""
    return await _download(run_id, f"/runs/{run_id}/files/report.md", f"report_{sanitize_filename(run_id)}.md")


@tool(READ)
async def read_run_file(
    run_id: RID,
    filename: Annotated[str, Field(description="Plain file name in the run folder, e.g. report.md, bugs.json, app_map.json")],
    max_chars: Annotated[int, Field(ge=100, le=20000)] = 8000,
) -> dict:
    """Read a generated text file from the run folder (report.md, bugs.json, app_map.json, ...).

    The name must be a plain file name: no slashes, '..' or absolute paths. The backend refuses secrets.
    """
    name = plain_filename(filename)
    text = await get_client().get_text(f"/runs/{run_id}/files/{name}")
    max_chars = max(100, min(int(max_chars), 20000))
    return {"filename": name, "content": trim(text, max_chars), "size_chars": len(text),
            "truncated": len(text) > max_chars,
            "next_step_hint": hint("Use export_run_archive to get everything on disk.")}
