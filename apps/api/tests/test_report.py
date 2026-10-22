"""Unit tests for report generator and metrics calculation (Prompt C5)."""

import json
import shutil
from pathlib import Path
import pytest

from app.config import settings
from app.models import (
    AppMap,
    BugsFile,
    Catalog,
    Results,
    ReviewLog,
    Run,
    RunInput,
    TestCase,
)
from app import report
from app import storage

TestCase.__test__ = False


@pytest.fixture
def temp_run(tmp_path, monkeypatch):
    """Fixture that redirects RUNS_DIR to tmp_path and seeds a done run from contracts/samples."""
    monkeypatch.setattr(settings, "runs_dir", tmp_path)
    run_id = "test-done-run"
    rdir = tmp_path / run_id
    rdir.mkdir(parents=True, exist_ok=True)

    samples_dir = settings.repo_root / "packages" / "contracts" / "samples"
    files_dir = samples_dir / "files"

    # Copy sample files
    shutil.copy(samples_dir / "app_map.sample.json", rdir / "app_map.json")
    shutil.copy(samples_dir / "catalog.sample.json", rdir / "catalog.json")
    shutil.copy(samples_dir / "results.sample.json", rdir / "results.json")
    shutil.copy(samples_dir / "bugs.sample.json", rdir / "bugs.json")
    shutil.copy(samples_dir / "review_log.sample.json", rdir / "review_log.json")
    shutil.copy(samples_dir / "metrics.sample.json", rdir / "metrics.json")

    # Read done view for run and input
    with open(samples_dir / "run_view.done.sample.json", "r", encoding="utf-8") as f:
        done_view = json.load(f)

    with open(rdir / "run.json", "w", encoding="utf-8") as f:
        json.dump(done_view["run"], f, indent=2)

    with open(rdir / "input.json", "w", encoding="utf-8") as f:
        json.dump(done_view["input"], f, indent=2)

    # Copy files/ evidence and scripts
    if files_dir.exists():
        if (files_dir / "evidence").exists():
            shutil.copytree(files_dir / "evidence", rdir / "evidence")
        if (files_dir / "scripts").exists():
            shutil.copytree(files_dir / "scripts", rdir / "scripts")

    # Seed secrets with a sensitive password string to verify zero leakage
    with open(rdir / "secrets.json", "w", encoding="utf-8") as f:
        json.dump({"password": "SUPER_SECRET_UNLEAKABLE_PASS_1234"}, f)

    return run_id


def test_build_metrics_calculates_correct_numbers(temp_run):
    m = report.build_metrics(temp_run)
    assert m.runId == temp_run
    assert m.wallClockSeconds > 0
    assert m.tests.planned == 11
    assert m.tests.approved == 11
    assert m.tests.passed == 3
    assert m.tests.failed == 9
    assert m.tests.errored == 1
    assert m.bugs.confirmed == 8
    assert m.bugs.flaky == 1
    assert m.bugs.notReproduced == 1
    assert m.coverage.specItems == 11
    assert m.coverage.specItemsCovered == 11

    # Verify metrics.json was persisted
    saved_m = storage.load_model(temp_run, "metrics.json", report.Metrics)
    assert saved_m is not None
    assert saved_m.wallClockSeconds == m.wallClockSeconds


def test_build_report_generates_all_sections_in_order(temp_run):
    report_text = report.build_report(temp_run)

    headings = [
        "# QA Report:",
        "## Summary",
        "## Confirmed bugs",
        "## Flaky bugs",
        "## Not reproduced",
        "## Test results",
        "## Coverage",
        "## Timings",
        "## Safety",
        "## Review log",
    ]

    last_pos = -1
    for h in headings:
        pos = report_text.find(h)
        assert pos != -1, f"Missing heading: {h}"
        assert pos > last_pos, f"Heading {h} is out of order"
        last_pos = pos

    # Verify confirmed bug title appears under Confirmed bugs
    assert "T02: Signup accepts an invalid email" in report_text
    assert "reproduced 3 of 3" in report_text

    # Verify flaky bug appears under Flaky bugs
    assert "T10: Every second settings save fails with HTTP 500" in report_text
    assert "reproduced 2 of 3 replays" in report_text

    # Verify unconfirmed bug appears in Not reproduced table
    assert "B08" in report_text

    # Evidence links resolve to files that exist
    rdir = storage.run_dir(temp_run)
    assert (rdir / "evidence" / "T02" / "screenshot.png").exists()
    assert "[screenshot](evidence/T02/screenshot.png)" in report_text

    # Verify secret password NEVER appears in report
    assert "SUPER_SECRET_UNLEAKABLE_PASS_1234" not in report_text


def test_report_with_zero_bugs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "runs_dir", tmp_path)
    run_id = "clean-run"
    rdir = tmp_path / run_id
    rdir.mkdir(parents=True, exist_ok=True)

    run = Run(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        updatedAt="2026-10-18T00:01:00Z",
        stage="done",
        mode="manual",
        targetUrl="http://localhost:4000",
    )
    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        targetUrl="http://localhost:4000",
        specRaw="S1: Happy path",
        spec=[],
    )
    catalog = Catalog(runId=run_id, generatedAt="2026-10-18T00:00:00Z", tests=[])
    bugs_file = BugsFile(runId=run_id, bugs=[])
    results = Results(runId=run_id, startedAt="2026-10-18T00:00:00Z", durationSeconds=5.0, workers=4, tests=[])

    storage.save_model(run_id, "run.json", run)
    storage.save_model(run_id, "input.json", run_input)
    storage.save_model(run_id, "catalog.json", catalog)
    storage.save_model(run_id, "bugs.json", bugs_file)
    storage.save_model(run_id, "results.json", results)

    report_text = report.build_report(run_id)
    assert "No bugs were confirmed." in report_text
    assert "No confirmed bugs." in report_text
    assert "No flaky bugs." in report_text
    # Manual mode must NOT have review log
    assert "## Review log" not in report_text


def test_pipes_and_newlines_in_titles_are_escaped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "runs_dir", tmp_path)
    run_id = "escape-test"
    rdir = tmp_path / run_id
    rdir.mkdir(parents=True, exist_ok=True)

    run = Run(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        updatedAt="2026-10-18T00:01:00Z",
        stage="done",
        mode="manual",
        targetUrl="http://localhost:4000",
    )
    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        targetUrl="http://localhost:4000",
        specRaw="S1: Check pipe | handling",
        spec=[],
    )
    test_case = TestCase(
        id="T01",
        title="Check pipe | and \n newline in title",
        description="desc",
        status="approved",
    )
    catalog = Catalog(runId=run_id, generatedAt="2026-10-18T00:00:00Z", tests=[test_case])
    bugs_file = BugsFile(runId=run_id, bugs=[])
    results = Results(runId=run_id, startedAt="2026-10-18T00:00:00Z", durationSeconds=2.0, workers=1, tests=[])

    storage.save_model(run_id, "run.json", run)
    storage.save_model(run_id, "input.json", run_input)
    storage.save_model(run_id, "catalog.json", catalog)
    storage.save_model(run_id, "bugs.json", bugs_file)
    storage.save_model(run_id, "results.json", results)

    report_text = report.build_report(run_id)
    # Check that pipe is escaped
    assert "\\|" in report_text
    # No raw newlines inside table cells
    for line in report_text.splitlines():
        if line.startswith("| T01"):
            assert "\n" not in line
