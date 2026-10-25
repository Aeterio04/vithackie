"""Execute a spec-driven catalog: run Playwright, build per-TC results with evidence."""

import base64
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from kawach.core.clock import now_iso
from kawach.execution.runner import (
    is_infrastructure_flake,
    normalize_path,
    parse_report,
    post_process_video,
    run_playwright,
)
from kawach.schemas import Catalog, Results, TestResult
from kawach.schemas.results import ResultsSummary
from kawach.storage import artifacts as storage

TC_RE = re.compile(r"^(TC-[A-Z0-9]+-\d{3})")
STATUS_TO_OUTCOME = {
    "passed": "passed",
    "passed_with_issues": "passed_with_issues",
    "failed": "assertion_failure",
    "script_error": "script_error",
    "safety_violation": "assertion_failure",
    "environment_error": "environment_error",
    "not_run": "not_run",
    "inconclusive": "inconclusive",
}
ENV_HINTS = re.compile(r"net::ERR_|ECONNRESET|ETIMEDOUT|ERR_CONNECTION|ERR_NAME_NOT_RESOLVED|captcha|access denied|Cloudflare|HTTP 403|HTTP 429|HTTP 50[234]", re.I)


def _read_attachment(att: Dict[str, Any]) -> Optional[bytes]:
    if att.get("body"):
        try:
            return base64.b64decode(att["body"])
        except Exception:
            return None
    p = att.get("path")
    if p and Path(p).exists():
        return Path(p).read_bytes()
    return None


def run_spec_tests(
    run_id: str,
    *,
    mode: str = "official",
    workers: int = 2,
    only: Optional[List[str]] = None,
    allowed_hosts: str = "www.imocha.io,imocha.io,app.imocha.io",
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run the generated TC scripts. `mode` names the output folders (calibration, official-1, ...)."""
    r_dir = storage.run_dir(run_id)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    approved = [t for t in (catalog.tests if catalog else []) if t.status == "approved" and t.scriptStatus == "ok"]
    ids = [t.id for t in approved if not only or t.id in only]

    rate_dir = r_dir / "rate" / mode
    if rate_dir.exists():
        shutil.rmtree(rate_dir, ignore_errors=True)
    rate_dir.mkdir(parents=True, exist_ok=True)
    preset = storage.read_json(run_id, "preset.json") or {}
    workers = int(preset.get("workers", workers))
    env = {
        "ALLOWED_HOSTS": allowed_hosts,
        "RATE_DIR": normalize_path(rate_dir),
        "RATE_LOG": normalize_path(rate_dir / "requests.jsonl"),
        "MAX_RPS": str(preset.get("maxRequestsPerSecond", 2)),
        "SPEC_BASE_URL": (preset.get("target") or "https://www.imocha.io/").rstrip("/"),
    }
    if preset.get("noiseRegex"):
        env["NOISE_RE"] = preset["noiseRegex"]
    if extra_env:
        env.update(extra_env)

    files = [f"scripts/{i}.spec.ts" for i in ids] if only else None
    started = now_iso()
    t0 = time.time()
    raw = run_playwright(run_id, workers=workers, out_name=mode, files=files, extra_env=env, timeout_s=3600)
    wall = time.time() - t0

    records = parse_report(raw.report_path) if raw.report_path else []
    by_id: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        m = TC_RE.match(rec["title"])
        if m:
            by_id[m.group(1)] = rec

    results: List[Dict[str, Any]] = []
    cat_by_id = {t.id: t for t in (catalog.tests if catalog else [])}
    for tid in ids:
        t = cat_by_id[tid]
        rec = by_id.get(tid)
        ev_dir = r_dir / "evidence" / mode / tid
        ev_dir.mkdir(parents=True, exist_ok=True)
        entry: Dict[str, Any] = {
            "id": tid, "title": t.title, "priority": t.priority, "specRefs": t.specRef, "type": t.tcType,
            "confidence": t.confidence, "viewport": t.viewport,
        }
        if rec is None:
            entry.update(status="not_run", errorMessage="No result in Playwright report", steps=[], expected=[], findings=[])
            results.append(entry)
            continue

        tc_json: Dict[str, Any] = {}
        video_dur, quality, reason = 0.0, "poor", "no video"
        for att in rec.get("attachments", []):
            name, ctype, apath = att.get("name", ""), att.get("contentType", ""), att.get("path")
            data = _read_attachment(att)
            if name == "tc_result.json" and data:
                try:
                    tc_json = json.loads(data.decode("utf-8"))
                except Exception:
                    pass
            elif name == "requests.json" and data:
                (ev_dir / "requests.json").write_bytes(data)
            elif name in ("console.json", "network.json") and data:
                (ev_dir / name).write_bytes(data)
            elif ctype == "video/webm" or name == "video":
                src = Path(apath) if apath and Path(apath).exists() else None
                if src:
                    video_dur, quality, reason = post_process_video(src, ev_dir / "video.webm")
            elif name == "trace" or (apath and Path(apath).name == "trace.zip"):
                if apath and Path(apath).exists():
                    shutil.copy2(apath, ev_dir / "trace.zip")
            elif ctype == "image/png" or name == "screenshot":
                if apath and Path(apath).exists():
                    shutil.copy2(apath, ev_dir / "screenshot.png")

        err = rec.get("errorMessage") or ""
        if tc_json:
            status = tc_json["status"]
            if status == "script_error" and ENV_HINTS.search(json.dumps(tc_json.get("steps", [])) + err):
                status = "environment_error"
            entry.update(
                status=status, steps=tc_json.get("steps", []), expected=tc_json.get("expected", []),
                findings=tc_json.get("findings", []), notes=tc_json.get("notes", []),
                durationMs=tc_json.get("durationMs", rec["durationMs"]), finalUrl=tc_json.get("finalUrl"),
                safetyViolations=tc_json.get("safetyViolations", []), nonGetRequests=tc_json.get("nonGetRequests", []),
                consoleErrors=tc_json.get("consoleErrors", []), pageErrors=tc_json.get("pageErrors", []),
                viewportUsed=tc_json.get("viewport"),
            )
        else:
            # Harness never wrote a result: crash/timeout before or after steps.
            status = "environment_error" if ENV_HINTS.search(err) else "script_error"
            entry.update(status=status, steps=[], expected=[], findings=[], durationMs=rec["durationMs"])
        entry["errorMessage"] = err[:800] if status not in ("passed", "passed_with_issues") else None
        entry["evidence"] = {
            "dir": f"evidence/{mode}/{tid}",
            "video": "video.webm" if (ev_dir / "video.webm").exists() else None,
            "screenshot": "screenshot.png" if (ev_dir / "screenshot.png").exists() else None,
            "trace": "trace.zip" if (ev_dir / "trace.zip").exists() else None,
            "videoDuration": video_dur, "videoQuality": quality, "videoReason": reason,
        }
        results.append(entry)

    # rate statistics (shared limiter log)
    rate = _rate_stats(rate_dir / "requests.jsonl")
    summary = {}
    for e in results:
        summary[e["status"]] = summary.get(e["status"], 0) + 1
    out = {
        "runId": run_id, "mode": mode, "startedAt": started, "durationSeconds": round(wall, 1), "workers": workers,
        "exitCode": raw.exit_code, "results": results, "summary": summary, "rate": rate,
        "stderrTail": (raw.stderr or "")[-600:],
    }
    storage.write_json(run_id, f"spec_results_{mode}.json", out)
    return out


def _rate_stats(path: Path) -> Dict[str, Any]:
    ts: List[int] = []
    kinds: Dict[str, int] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                ts.append(int(d["ts"]))
                kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
            except Exception:
                continue
    ts.sort()
    peak = 0
    j = 0
    for i in range(len(ts)):
        while ts[i] - ts[j] >= 1000:
            j += 1
        peak = max(peak, i - j + 1)
    return {"gatedRequests": len(ts), "peakRequestsInAnyOneSecondWindow": peak, "byKind": kinds,
            "spanSeconds": round((ts[-1] - ts[0]) / 1000, 1) if ts else 0}


def write_results_model(run_id: str, data: Dict[str, Any]) -> Results:
    """Persist results.json in the platform's Results schema so existing views keep working."""
    tests = []
    summ = ResultsSummary()
    for e in data["results"]:
        outcome = STATUS_TO_OUTCOME.get(e["status"], "inconclusive")
        ev = e.get("evidence") or {}
        tests.append(TestResult(
            testId=e["id"], title=e["title"], file=f"scripts/{e['id']}.spec.ts", source="planned", outcome=outcome,
            durationMs=int(e.get("durationMs", 0)), errorMessage=e.get("errorMessage"),
            evidenceDir=ev.get("dir"), totalSteps=len(e.get("steps", [])),
            videoDuration=ev.get("videoDuration"), evidenceQuality=ev.get("videoQuality"),
            failureType=e["status"] if e["status"] not in ("passed", "passed_with_issues") else None,
        ))
        summ.total += 1
        key = {"passed": "passed", "passed_with_issues": "passedWithIssues", "assertion_failure": "assertionFailures",
               "script_error": "scriptErrors", "environment_error": "environmentErrors", "not_run": "notRun",
               "inconclusive": "inconclusive"}.get(outcome)
        if key:
            setattr(summ, key, getattr(summ, key) + 1)
        if outcome == "assertion_failure":
            summ.failed += 1
    res = Results(runId=run_id, startedAt=data["startedAt"], durationSeconds=data["durationSeconds"],
                  workers=data["workers"], tests=tests, summary=summ)
    storage.save_model(run_id, "results.json", res)
    return res


def run_selected(run_id: str, mode: str = "official") -> Dict[str, Any]:
    """Run the approved TCs of the run's priority tier; every other approved TC is recorded as not_run.

    Fails loudly (raises) when tests were selected but none executed.
    """
    from kawach.schemas import RunInput
    from kawach.services.spec_driven import selected_test_ids

    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    ri = storage.load_model(run_id, "input.json", RunInput)
    tier = ri.priorityTier if ri else None
    approved = [t for t in (catalog.tests if catalog else []) if t.status == "approved"]
    sel = selected_test_ids(catalog, tier)
    out = run_spec_tests(run_id, mode=mode, workers=2, only=sel if len(sel) < len(approved) else None)
    skipped = [t for t in approved if t.id not in sel]
    for t in skipped:
        out["results"].append({
            "id": t.id, "title": t.title, "priority": t.priority, "specRefs": t.specRef, "type": t.tcType,
            "confidence": t.confidence, "viewport": t.viewport, "status": "not_run",
            "errorMessage": f"Outside the selected priority tier ({tier})", "steps": [], "expected": [], "findings": [],
        })
    out["tier"] = tier or "all"
    out["selected"] = len(sel)
    out["executed"] = len([r for r in out["results"] if r["id"] in sel and r["status"] != "not_run"])
    out["summary"] = {}
    for e in out["results"]:
        out["summary"][e["status"]] = out["summary"].get(e["status"], 0) + 1
    storage.write_json(run_id, f"spec_results_{mode}.json", out)
    write_results_model(run_id, out)
    if sel and out["executed"] == 0:
        raise RuntimeError(f"0 of {len(sel)} selected tests executed ({out.get('stderrTail', '')[-200:]})")
    return out
