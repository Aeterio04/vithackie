"""Unit tests for Bug Reporter and Reviewer agents."""

import json
from unittest.mock import MagicMock
import pytest

from app.agents import bug_reporter, reviewer
from app.config import settings
from app.models import Bug, BugsFile, Catalog, ReviewLog, Run, RunInput, SpecItem
from app import storage


@pytest.fixture
def run_fixture(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")

    run_id = "test-bugs-run-001"
    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        targetUrl="http://localhost:4000",
        prompt="Testing bug reporter",
        specRaw="S1: Signup\nS2: Invalid email",
        spec=[SpecItem(id="S2", text="Enter a valid email address")],
        username="qa.tester@example.com",
    )
    storage.save_model(run_id, "input.json", run_input)

    run_obj = Run(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        updatedAt="2026-10-18T00:00:00Z",
        stage="running",
        mode="manual",
        targetUrl="http://localhost:4000",
    )
    storage.save_model(run_id, "run.json", run_obj)

    # Load samples
    catalog_sample = settings.repo_root / "packages" / "contracts" / "samples" / "catalog.sample.json"
    with open(catalog_sample, "r", encoding="utf-8") as f:
        cat_data = json.load(f)
    storage.write_json(run_id, "catalog.json", cat_data)

    bugs_sample = settings.repo_root / "packages" / "contracts" / "samples" / "bugs.sample.json"
    with open(bugs_sample, "r", encoding="utf-8") as f:
        bugs_data = json.load(f)
    storage.write_json(run_id, "bugs.json", bugs_data)

    return run_id


def test_write_bug_reports_with_fake_llm(run_fixture):
    run_id = run_fixture
    bugs = bug_reporter.write_bug_reports(run_id)

    assert len(bugs) >= 9
    for b in bugs:
        assert b.title != ""
        assert len(b.steps) > 0
        assert b.expected != ""
        assert b.actual != ""
        # IDs and immutable metadata untouched
        assert b.id.startswith("B")
        assert b.status in ("candidate", "confirmed", "flaky", "not_reproduced")


def test_write_bug_reports_coerces_invalid_severity(run_fixture, monkeypatch):
    run_id = run_fixture
    llm = bug_reporter.get_llm()

    mock_report = {
        "title": "Catastrophic error",
        "category": "validation",
        "severity": "catastrophic",  # Invalid severity value
        "steps": ["Step 1", "Step 2"],
        "expected": "Expected result",
        "actual": "Actual result",
    }
    monkeypatch.setattr(llm, "complete_json", MagicMock(return_value=mock_report))

    # Test on a single bug
    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
    bugs_file.bugs = [bugs_file.bugs[0]]
    storage.save_model(run_id, "bugs.json", bugs_file)

    bugs = bug_reporter.write_bug_reports(run_id)
    assert bugs[0].severity == "medium"  # Coerced to default


def test_write_bug_reports_fail_soft_on_single_bug(run_fixture, monkeypatch):
    run_id = run_fixture
    llm = bug_reporter.get_llm()

    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
    bugs_file.bugs = bugs_file.bugs[:2]
    storage.save_model(run_id, "bugs.json", bugs_file)

    # Bug 1 succeeds, Bug 2 raises an exception
    valid_report = {
        "title": "Bug 1 title",
        "category": "validation",
        "severity": "high",
        "steps": ["Step 1"],
        "expected": "Exp",
        "actual": "Act",
    }
    mock_llm = MagicMock(side_effect=[valid_report, RuntimeError("LLM network crash")])
    monkeypatch.setattr(llm, "complete_json", mock_llm)

    bugs = bug_reporter.write_bug_reports(run_id)
    assert len(bugs) == 2
    assert bugs[0].title == "Bug 1 title"
    assert bugs[1].title != ""  # Fallback generated
    assert bugs[1].category == "other"
    assert len(bugs[1].steps) > 0


def test_write_bug_reports_exploratory_bug_without_catalog(run_fixture):
    run_id = run_fixture
    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)

    # Create exploratory bug with testId "X02" not in catalog
    exploratory_bug = Bug(
        id="B99",
        testId="X02",
        source="exploratory",
        title="X02: /settings reload mid-flow",
        grep="X02:",
        file="probes/X02.ts",
        category="navigation",
        severity="medium",
        specRef=[],
        steps=[],
        expected="",
        actual="",
        errorMessage="expect(received).toBe(true)\nReceived: false",
        signature="sig123",
        duplicates=[],
        status="candidate",
    )
    bugs_file.bugs = [exploratory_bug]
    storage.save_model(run_id, "bugs.json", bugs_file)

    bugs = bug_reporter.write_bug_reports(run_id)
    assert len(bugs) == 1
    assert bugs[0].id == "B99"
    assert bugs[0].title != ""
    assert len(bugs[0].steps) > 0


def test_review_catalog_autonomous_mode(run_fixture):
    run_id = run_fixture
    # Ensure tests are in 'proposed' state so reviewer can evaluate them
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    for t in catalog.tests:
        t.status = "proposed"
    storage.save_model(run_id, "catalog.json", catalog)

    review_log = reviewer.review_catalog(run_id)

    assert isinstance(review_log, ReviewLog)
    assert len(review_log.decisions) > 0
    assert all(d.decision == "approve" for d in review_log.decisions)

    # Verify catalog status changed to approved
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    assert all(t.status == "approved" for t in catalog.tests)
