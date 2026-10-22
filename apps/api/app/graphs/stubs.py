"""STUB_MODE handlers for faking each pipeline stage from contracts/samples."""

import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.config import settings
from app.models import BugsFile, Catalog, ReviewLog
from app import storage

SAMPLES_DIR = settings.repo_root / "packages" / "contracts" / "samples"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stub_explore(run_id: str) -> None:
    """Fake the explore stage using app_map.sample.json."""
    storage.set_stage(run_id, "exploring", step="Crawling application pages (stub)", done=4, total=10)
    time.sleep(1.0)

    sample_file = SAMPLES_DIR / "app_map.sample.json"
    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["generatedAt"] = _now_iso()
    storage.write_json(run_id, "explore_raw.json", data)
    storage.write_json(run_id, "app_map.json", data)


def stub_plan(run_id: str) -> None:
    """Fake the planning stage using catalog.sample.json."""
    storage.set_stage(run_id, "planning", step="Designing test catalog (stub)", done=6, total=12)
    time.sleep(1.0)

    sample_file = SAMPLES_DIR / "catalog.sample.json"
    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["runId"] = run_id
    data["generatedAt"] = _now_iso()

    # Reset all tests to proposed / pending
    for t in data.get("tests", []):
        t["status"] = "proposed"
        t["script"] = None
        t["scriptStatus"] = "pending"
        t["scriptError"] = None

    storage.write_json(run_id, "catalog.json", data)


def stub_review_gate(run_id: str) -> None:
    """Fake the autonomous review gate stage using review_log.sample.json."""
    storage.set_stage(run_id, "planning", step="Reviewer agent checking catalog (stub)", done=12, total=12)
    time.sleep(1.0)

    sample_file = SAMPLES_DIR / "review_log.sample.json"
    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["runId"] = run_id
    data["reviewedAt"] = _now_iso()
    storage.write_json(run_id, "review_log.json", data)

    # Mark all tests approved in catalog
    cat_data = storage.read_json(run_id, "catalog.json")
    if cat_data:
        for t in cat_data.get("tests", []):
            t["status"] = "approved"
        storage.write_json(run_id, "catalog.json", cat_data)

    storage.set_stage(run_id, "scripting", step="Review complete (stub)")


def stub_write_scripts(run_id: str) -> None:
    """Fake the script writing stage by generating .spec.ts files for approved tests."""
    cat_data = storage.read_json(run_id, "catalog.json")
    if not cat_data:
        return

    approved = [t for t in cat_data.get("tests", []) if t.get("status") == "approved"]
    storage.set_stage(run_id, "scripting", step="Writing Playwright scripts (stub)", done=0, total=len(approved))

    sample_script_file = SAMPLES_DIR / "files" / "scripts" / "T02.spec.ts"
    template_code = sample_script_file.read_text(encoding="utf-8") if sample_script_file.exists() else """import { test, expect } from '../../../apps/runner/fixtures';
test('T02: Placeholder', async ({ page }) => { await page.goto('/login'); });"""

    scripts_dir = storage.run_dir(run_id) / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    for idx, test_item in enumerate(approved):
        tid = test_item.get("id", f"T{idx+1:02d}")
        # Rewrite T02 in title to tid
        code = re.sub(r"test\(\s*(['\"`])T\d+:\s*(.*?)\1", rf"test(\1{tid}: \2\1", template_code)
        script_file = scripts_dir / f"{tid}.spec.ts"
        script_file.write_text(code, encoding="utf-8")

        test_item["script"] = f"scripts/{tid}.spec.ts"
        test_item["scriptStatus"] = "ok"

    storage.write_json(run_id, "catalog.json", cat_data)
    time.sleep(1.0)


def stub_run_tests(run_id: str) -> None:
    """Fake test execution, results, and evidence generation."""
    storage.set_stage(run_id, "running", step="Executing test suite (stub)", done=6, total=12)
    time.sleep(1.0)

    # 1. results.json
    results_sample = SAMPLES_DIR / "results.sample.json"
    with open(results_sample, "r", encoding="utf-8") as f:
        res_data = json.load(f)
    res_data["runId"] = run_id
    res_data["startedAt"] = _now_iso()
    storage.write_json(run_id, "results.json", res_data)

    # 2. bugs.json (initial state: candidate, replay: null)
    bugs_sample = SAMPLES_DIR / "bugs.sample.json"
    with open(bugs_sample, "r", encoding="utf-8") as f:
        bugs_data = json.load(f)
    bugs_data["runId"] = run_id
    for b in bugs_data.get("bugs", []):
        b["status"] = "candidate"
        b["replay"] = None
    storage.write_json(run_id, "bugs.json", bugs_data)

    # 3. copy sample evidence
    evidence_src = SAMPLES_DIR / "files" / "evidence"
    evidence_dest = storage.run_dir(run_id) / "evidence"
    if evidence_src.exists():
        if evidence_dest.exists():
            shutil.rmtree(evidence_dest)
        shutil.copytree(evidence_src, evidence_dest)

    # 4. blocked_requests.jsonl
    blocked_file = storage.run_dir(run_id) / "blocked_requests.jsonl"
    blocked_file.write_text(
        '{"url": "https://evil-tracker.com/pixel.png", "status": "blocked", "reason": "off_domain"}\n'
        '{"url": "https://analytics-out.com/event", "status": "blocked", "reason": "off_domain"}\n',
        encoding="utf-8",
    )


def stub_report_bugs(run_id: str) -> None:
    """Fake defect reporting stage."""
    storage.set_stage(run_id, "verifying", step="Writing bug reports (stub)", done=4, total=8)
    time.sleep(1.0)


def stub_verify(run_id: str) -> None:
    """Fake verification stage, replaying and writing verification files."""
    storage.set_stage(run_id, "verifying", step="Replaying bug candidates (stub)", done=8, total=8)
    time.sleep(1.0)

    # Load target statuses from bugs.sample.json
    bugs_sample = SAMPLES_DIR / "bugs.sample.json"
    with open(bugs_sample, "r", encoding="utf-8") as f:
        orig_bugs = json.load(f)

    status_map = {b["id"]: (b.get("status", "confirmed"), b.get("replay")) for b in orig_bugs.get("bugs", [])}

    cur_bugs = storage.read_json(run_id, "bugs.json")
    verif_dir = storage.run_dir(run_id) / "verification"
    verif_dir.mkdir(parents=True, exist_ok=True)

    if cur_bugs:
        for b in cur_bugs.get("bugs", []):
            bid = b["id"]
            stat, rep = status_map.get(bid, ("confirmed", {"reproduced": 3, "attempts": 3}))
            b["status"] = stat
            b["replay"] = rep

            verif_data = {
                "bugId": bid,
                "verifiedAt": _now_iso(),
                "status": stat,
                "attempts": [
                    {"attempt": 1, "reproduced": stat in ("confirmed", "flaky"), "outcome": "failed", "durationMs": 420},
                    {"attempt": 2, "reproduced": stat in ("confirmed", "flaky"), "outcome": "failed", "durationMs": 410},
                    {"attempt": 3, "reproduced": stat == "confirmed", "outcome": "failed" if stat == "confirmed" else "passed", "durationMs": 395},
                ],
            }
            storage.write_json(run_id, f"verification/{bid}.json", verif_data)

        storage.write_json(run_id, "bugs.json", cur_bugs)


def stub_build_report(run_id: str) -> None:
    """Fake final report and metrics generation."""
    storage.set_stage(run_id, "reporting", step="Compiling metrics and report (stub)", done=10, total=10)
    time.sleep(1.0)

    from app import report
    try:
        report.build_report(run_id)
    except Exception:
        metrics_sample = SAMPLES_DIR / "metrics.sample.json"
        if metrics_sample.exists():
            with open(metrics_sample, "r", encoding="utf-8") as f:
                m_data = json.load(f)
            m_data["runId"] = run_id
            storage.write_json(run_id, "metrics.json", m_data)

        report_sample = SAMPLES_DIR / "files" / "report.md"
        if report_sample.exists():
            target_md = storage.run_dir(run_id) / "report.md"
            shutil.copy2(report_sample, target_md)

