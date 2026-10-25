"""Unit and integration tests for the reliable Markdown, HTML, and PDF Report Generator."""

import json
import os
from pathlib import Path
import time
from typing import Any, Dict
import pytest
import pypdf

from kawach.core.config import settings
from kawach.core.clock import now_iso
from kawach.schemas import (
    AppMap,
    BugsFile,
    Bug,
    BugReplay,
    Catalog,
    Evidence,
    HeadingInfo,
    LinkInfo,
    PageInfo,
    Results,
    ResultsSummary,
    ReviewDecision,
    ReviewLog,
    Run,
    RunInput,
    SpecItem,
    Step,
    TestCase,
    TestResult,
)
from kawach.storage import artifacts as storage
from kawach.execution.report_generator import generate_all_reports

TestCase.__test__ = False
TestResult.__test__ = False


@pytest.fixture
def run_fixture_dir(tmp_path, monkeypatch):
    """Set runs_dir to tmp_path for isolated report generation tests."""
    monkeypatch.setattr(settings, "runs_dir", tmp_path / "runs")
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)
    return tmp_path / "runs"


def _create_test_run(
    run_id: str,
    spec_items: list,
    tests: list,
    test_results: list,
    bugs: list,
    verifications: dict = None,
    review_decisions: list = None,
    stage: str = "done",
    mode: str = "manual",
) -> Path:
    """Helper to stage a complete or partial run directory."""
    r_dir = storage.run_dir(run_id)

    run = Run(
        runId=run_id,
        createdAt=now_iso(),
        updatedAt=now_iso(),
        stage=stage,
        mode=mode,
        targetUrl="http://localhost:5173",
        report_status="pending",
    )
    storage.save_model(run_id, "run.json", run)

    run_input = RunInput(
        runId=run_id,
        createdAt=now_iso(),
        targetUrl="http://localhost:5173",
        spec=[SpecItem(id=s["id"], text=s["text"]) for s in spec_items],
        mode=mode,
    )
    storage.save_model(run_id, "input.json", run_input)

    cat_tests = []
    for t in tests:
        cat_tests.append(
            TestCase(
                id=t["id"],
                title=t["title"],
                description=t.get("desc", ""),
                specRef=t.get("specRef", []),
                priority=t.get("priority", "medium"),
                category=t.get("category", "single_step"),
                status=t.get("status", "approved"),
                steps=[Step(n=i+1, action=st) for i, st in enumerate(t.get("steps", ["Step 1"]))],
            )
        )
    storage.save_model(run_id, "catalog.json", Catalog(runId=run_id, generatedAt=now_iso(), tests=cat_tests))

    res_tests = []
    for tr in test_results:
        res_tests.append(
            TestResult(
                testId=tr["testId"],
                title=tr.get("title", ""),
                file=f"scripts/{tr['testId']}.spec.ts",
                source="planned",
                outcome=tr["outcome"],
                durationMs=tr.get("durationMs", 1500),
                errorMessage=tr.get("errorMessage"),
                evidenceDir=f"evidence/{tr['testId']}",
            )
        )
    res_summary = ResultsSummary(
        total=len(res_tests),
        passed=sum(1 for r in res_tests if r.outcome == "passed"),
        assertionFailures=sum(1 for r in res_tests if r.outcome == "assertion_failure"),
        testErrors=sum(1 for r in res_tests if r.outcome == "test_error"),
    )
    storage.save_model(
        run_id,
        "results.json",
        Results(
            runId=run_id,
            startedAt=now_iso(),
            durationSeconds=45.0,
            workers=2,
            tests=res_tests,
            summary=res_summary,
        ),
    )

    bug_objects = []
    for b in bugs:
        bug_objects.append(
            Bug(
                id=b["id"],
                testId=b.get("testId", "T01"),
                source="planned",
                title=b["title"],
                grep=b["id"],
                file=f"repro/{b['id']}_repro.spec.ts",
                category=b.get("category", "auth"),
                severity=b.get("severity", "high"),
                specRef=b.get("specRef", []),
                steps=b.get("steps", ["Step 1", "Step 2"]),
                expected=b.get("expected", "Expected error"),
                actual=b.get("actual", "Actual failure"),
                errorMessage=b.get("errorMessage", "Assertion failed"),
                signature=f"sig_{b['id']}",
                status=b.get("status", "confirmed"),
            )
        )
    storage.save_model(run_id, "bugs.json", BugsFile(runId=run_id, bugs=bug_objects))

    app_map = AppMap(
        baseUrl="http://localhost:5173",
        generatedAt=now_iso(),
        pages=[
            PageInfo(
                url="http://localhost:5173/",
                path="/",
                title="Home Page",
                status=200,
                links=[LinkInfo(text="Login", href="/login")],
                interactiveElements=["btn1", "btn2"],
            ),
            PageInfo(
                url="http://localhost:5173/login",
                path="/login",
                title="Login Page",
                status=200,
                forms=[],
                interactiveElements=["email", "pass", "submit"],
            ),
        ],
    )
    storage.save_model(run_id, "app_map.json", app_map)

    if review_decisions:
        r_log = ReviewLog(
            runId=run_id,
            reviewedAt=now_iso(),
            decisions=[
                ReviewDecision(
                    testId=rd["testId"],
                    decision=rd["decision"],
                    reason=rd.get("reason", "Standard review policy"),
                )
                for rd in review_decisions
            ],
        )
        storage.save_model(run_id, "review_log.json", r_log)

    if verifications:
        for bid, v_data in verifications.items():
            storage.write_json(run_id, f"verification/{bid}.json", v_data)

    return r_dir


def test_normal_run_full_lifecycle(run_fixture_dir):
    """Test normal run with passes, failures, 2 confirmed bugs, 1 flaky, 1 not reproduced, and rejected tests."""
    run_id = "test-run-normal-01"
    spec = [
        {"id": "S1", "text": "Users can authenticate with demo credentials"},
        {"id": "S2", "text": "Invalid email formats are rejected"},
        {"id": "S3", "text": "Products can be filtered by category"},
    ]
    tests = [
        {"id": "T01", "title": "Verify login valid email", "specRef": ["S1"], "status": "approved"},
        {"id": "T02", "title": "Verify login invalid email", "specRef": ["S2"], "status": "approved"},
        {"id": "T03", "title": "Verify filter by category", "specRef": ["S3"], "status": "approved"},
        {"id": "T04", "title": "Verify rejected test proposal", "specRef": ["S3"], "status": "rejected"},
    ]
    test_results = [
        {"testId": "T01", "outcome": "passed", "durationMs": 1200},
        {"testId": "T02", "outcome": "assertion_failure", "durationMs": 2400, "errorMessage": "Error: expect(received).toBe(true)"},
        {"testId": "T03", "outcome": "assertion_failure", "durationMs": 3100, "errorMessage": "TimeoutError: category button not found"},
    ]
    bugs = [
        {"id": "B01", "testId": "T02", "title": "Invalid email accepted", "severity": "high", "specRef": ["S2"], "status": "confirmed"},
        {"id": "B02", "testId": "T03", "title": "Category filter broken", "severity": "critical", "specRef": ["S3"], "status": "confirmed"},
        {"id": "B03", "testId": "T01", "title": "Flaky cart animation", "severity": "medium", "specRef": ["S1"], "status": "flaky"},
        {"id": "B04", "testId": "T01", "title": "Transient 500 error", "severity": "low", "specRef": ["S1"], "status": "not_reproduced"},
    ]
    verifications = {
        "B01": {
            "bugId": "B01",
            "attempts": [
                {"attempt": 1, "reproduced": True, "outcome": "assertion_failure", "durationMs": 1100},
                {"attempt": 2, "reproduced": True, "outcome": "assertion_failure", "durationMs": 1250},
                {"attempt": 3, "reproduced": True, "outcome": "assertion_failure", "durationMs": 1050},
            ],
            "reproduced": 3,
        },
        "B02": {
            "bugId": "B02",
            "attempts": [
                {"attempt": 1, "reproduced": True, "outcome": "assertion_failure", "durationMs": 1800},
                {"attempt": 2, "reproduced": True, "outcome": "assertion_failure", "durationMs": 1950},
                {"attempt": 3, "reproduced": True, "outcome": "assertion_failure", "durationMs": 1720},
            ],
            "reproduced": 3,
        },
        "B03": {
            "bugId": "B03",
            "attempts": [
                {"attempt": 1, "reproduced": True, "outcome": "assertion_failure", "durationMs": 850},
                {"attempt": 2, "reproduced": False, "outcome": "passed", "durationMs": 620},
                {"attempt": 3, "reproduced": False, "outcome": "passed", "durationMs": 610},
            ],
            "reproduced": 1,
        },
        "B04": {
            "bugId": "B04",
            "attempts": [
                {"attempt": 1, "reproduced": False, "outcome": "passed", "durationMs": 400},
                {"attempt": 2, "reproduced": False, "outcome": "passed", "durationMs": 410},
                {"attempt": 3, "reproduced": False, "outcome": "passed", "durationMs": 405},
            ],
            "reproduced": 0,
        },
    }
    review = [
        {"testId": "T01", "decision": "approve", "reason": "Valid auth flow"},
        {"testId": "T04", "decision": "reject", "reason": "Violates safety depth budget"},
    ]

    r_dir = _create_test_run(run_id, spec, tests, test_results, bugs, verifications, review)

    # Execute generation
    res = generate_all_reports(run_id)

    assert res["status"] == "ready"
    assert (r_dir / "report.md").exists()
    assert (r_dir / "report.html").exists()
    assert (r_dir / "report.pdf").exists()

    md = res["markdown"]

    # 1. Markdown contains every test ID
    assert "T01" in md
    assert "T02" in md
    assert "T03" in md
    assert "T04" in md

    # 2. Every spec item in coverage matrix
    assert "S1" in md
    assert "S2" in md
    assert "S3" in md

    # 3. Rejected test listed in rejected section
    assert "Rejected Tests at Review Gate" in md
    assert "Violates safety depth budget" in md

    # 4. Verified counts
    assert "2 confirmed" in md
    assert "1 flaky" in md
    assert "Not Reproduced" in md

    # 5. No placeholder or broken string literals
    for bad in ["undefined", "None", "NaN"]:
        # Only allow 'None' if part of descriptive text like 'specRef else None'
        assert f" {bad} " not in md, f"Found unexpected literal '{bad}' in markdown"

    # 6. Verify PDF validity
    reader = pypdf.PdfReader(str(r_dir / "report.pdf"))
    assert len(reader.pages) > 0
    pdf_text = "".join(p.extract_text() for p in reader.pages)
    assert run_id in pdf_text
    assert "Table of Contents" in pdf_text or "Executive Summary" in pdf_text
    assert "B01" in pdf_text

    # 7. Check run.json report_status
    saved_run = storage.load_model(run_id, "run.json", Run)
    assert saved_run.report_status == "ready"


def test_zero_bugs_run(run_fixture_dir):
    """Test run with zero defects."""
    run_id = "test-run-zero-bugs"
    spec = [{"id": "S1", "text": "Happy path works"}]
    tests = [{"id": "T01", "title": "Check home page", "specRef": ["S1"], "status": "approved"}]
    test_results = [{"testId": "T01", "outcome": "passed", "durationMs": 800}]

    r_dir = _create_test_run(run_id, spec, tests, test_results, bugs=[])
    res = generate_all_reports(run_id)

    assert res["status"] == "ready"
    md = res["markdown"]
    assert "0 confirmed defects" in md
    assert "No defects met the 3/3 confirmed replay requirement" in md
    assert (r_dir / "report.pdf").exists()


def test_failed_or_cancelled_partial_run(run_fixture_dir):
    """Test partial data from a failed or cancelled run."""
    run_id = "test-run-partial-fail"
    r_dir = _create_test_run(run_id, spec_items=[], tests=[], test_results=[], bugs=[], stage="failed")

    res = generate_all_reports(run_id)
    assert res["status"] == "ready"
    assert (r_dir / "report.md").exists()
    assert (r_dir / "report.pdf").exists()

    md = res["markdown"]
    assert "failed" in md


def test_missing_screenshots_graceful_handling(run_fixture_dir):
    """Ensure missing screenshots do not break report generation."""
    run_id = "test-run-missing-images"
    spec = [{"id": "S1", "text": "Feature S1"}]
    tests = [{"id": "T01", "title": "Test with missing screenshot", "specRef": ["S1"], "status": "approved"}]
    test_results = [{"testId": "T01", "outcome": "assertion_failure", "durationMs": 500}]

    r_dir = _create_test_run(run_id, spec, tests, test_results, bugs=[])
    res = generate_all_reports(run_id)

    assert res["status"] == "ready"
    assert (r_dir / "report.pdf").exists()


def test_special_characters_pipes_and_long_text(run_fixture_dir):
    """Ensure pipes, newlines in table cells, and long text are safely formatted."""
    run_id = "test-run-special-chars"
    long_desc = "A" * 1500
    spec = [{"id": "S1", "text": "Test requirement with | pipes | and \n newlines"}]
    tests = [{
        "id": "T01",
        "title": "Special chars test: | pipe | in title 🚀",
        "desc": long_desc,
        "specRef": ["S1"],
        "status": "approved",
    }]
    test_results = [{"testId": "T01", "outcome": "passed", "durationMs": 900}]

    r_dir = _create_test_run(run_id, spec, tests, test_results, bugs=[])
    res = generate_all_reports(run_id)

    assert res["status"] == "ready"
    md = res["markdown"]

    # Assert pipes in cells are escaped
    assert "\\|" in md
    assert (r_dir / "report.pdf").exists()


def test_large_scale_150_tests_performance(run_fixture_dir):
    """Ensure generation of 150+ tests completes well under 30 seconds."""
    run_id = "test-run-150-tests"
    spec = [{"id": f"S{i}", "text": f"Requirement S{i}"} for i in range(1, 20)]
    tests = []
    test_results = []
    for i in range(1, 155):
        tid = f"T{i:03d}"
        sref = f"S{(i % 19) + 1}"
        tests.append({"id": tid, "title": f"Automated performance test {tid}", "specRef": [sref], "status": "approved"})
        outcome = "passed" if i % 10 != 0 else "assertion_failure"
        test_results.append({"testId": tid, "outcome": outcome, "durationMs": 500 + i})

    _create_test_run(run_id, spec, tests, test_results, bugs=[])

    start_time = time.time()
    res = generate_all_reports(run_id)
    elapsed = time.time() - start_time

    assert res["status"] == "ready"
    assert elapsed < 30.0, f"Generation took {elapsed:.2f}s, exceeding 30s cap"


def test_missing_or_placeholder_verification_data_shows_unverified(run_fixture_dir):
    """Ensure defects with missing or placeholder verification data are labeled UNVERIFIED."""
    run_id = "test-run-unverified-check"
    spec = [{"id": "S1", "text": "Requirement S1"}]
    tests = [{"id": "T01", "title": "Test 1", "specRef": ["S1"], "status": "approved"}]
    test_results = [{"testId": "T01", "outcome": "assertion_failure"}]
    bugs = [
        # B01 has placeholder identical duration across attempts
        {"id": "B01", "testId": "T01", "title": "Placeholder bug", "severity": "high", "specRef": ["S1"], "status": "candidate"},
        # B02 has missing verification file
        {"id": "B02", "testId": "T01", "title": "Missing verif bug", "severity": "medium", "specRef": ["S1"], "status": "candidate"},
    ]
    # B01 has identical 1000ms durations
    verifications = {
        "B01": {
            "bugId": "B01",
            "attempts": [
                {"attempt": 1, "reproduced": True, "outcome": "assertion_failure", "durationMs": 1000},
                {"attempt": 2, "reproduced": True, "outcome": "assertion_failure", "durationMs": 1000},
                {"attempt": 3, "reproduced": True, "outcome": "assertion_failure", "durationMs": 1000},
            ],
        }
    }

    _create_test_run(run_id, spec, tests, test_results, bugs, verifications)
    res = generate_all_reports(run_id)

    assert res["status"] == "ready"
    md = res["markdown"]
    assert "Unverified Defect Candidates" in md
    assert "B01" in md
    assert "B02" in md
    assert "UNVERIFIED" in md
    # Confirmed count should be 0
    assert "0 confirmed" in md


def test_api_report_endpoints_pdf_markdown_regenerate(tmp_path, monkeypatch):
    """Test HTTP endpoints for GET report.pdf, GET report.md, and POST report/regenerate."""
    from fastapi.testclient import TestClient
    from kawach.main import app
    from kawach.db.models.runs import Run as DbRun
    from kawach.db.models.project import Project as DbProject
    from kawach.db.models.identity import User as DbUser
    from kawach.db.session import get_db, SessionLocal
    from kawach.services.auth_service import AuthService

    monkeypatch.setattr(settings, "runs_dir", tmp_path / "runs")
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)

    run_id = "test-endpoint-run-01"
    spec = [{"id": "S1", "text": "Endpoint auth test"}]
    tests = [{"id": "T01", "title": "Check endpoints", "specRef": ["S1"], "status": "approved"}]
    test_results = [{"testId": "T01", "outcome": "passed", "durationMs": 950}]
    _create_test_run(run_id, spec, tests, test_results, bugs=[])

    # Stage DB users and run ownership
    with SessionLocal() as db:
        user = db.get(DbUser, "user-123")
        if not user:
            user = DbUser(id="user-123", email="user@example.com", password_hash="hash", is_active=True)
            db.add(user)
            db.commit()

        other_user = db.get(DbUser, "user-other-999")
        if not other_user:
            other_user = DbUser(id="user-other-999", email="other@example.com", password_hash="hash", is_active=True)
            db.add(other_user)
            db.commit()

        proj = db.query(DbProject).first()
        if not proj:
            proj = DbProject(name="Test Proj", slug="test-proj", target_url="http://localhost:5173", owner_id="user-123")
            db.add(proj)
            db.commit()
            db.refresh(proj)

        db_run = db.query(DbRun).filter(DbRun.id == run_id).first()
        if not db_run:
            db_run = DbRun(
                id=run_id,
                project_id=proj.id,
                created_by="user-123",
                mode="manual",
                stage="done",
            )
            db.add(db_run)
            db.commit()

        auth_svc = AuthService(db)
        token = auth_svc.create_access_token("user-123", "user@example.com")
        other_token = auth_svc.create_access_token("user-other-999", "other@example.com")

    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})

    # 1. Test POST /api/v1/runs/{id}/report/regenerate
    regen_res = client.post(f"/api/v1/runs/{run_id}/report/regenerate")
    assert regen_res.status_code == 200, f"Regenerate failed: {regen_res.text}"
    regen_json = regen_res.json()
    assert regen_json["report_status"] == "ready"
    assert regen_json["has_pdf"] is True
    assert regen_json["has_md"] is True

    # 2. Test GET /api/v1/runs/{id}/report.pdf
    pdf_res = client.get(f"/api/v1/runs/{run_id}/report.pdf")
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers.get("content-type", "")
    assert len(pdf_res.content) > 1000

    # 3. Test GET /api/v1/runs/{id}/report.md
    md_res = client.get(f"/api/v1/runs/{run_id}/report.md")
    assert md_res.status_code == 200
    assert "text/markdown" in md_res.headers.get("content-type", "")
    assert f"#{run_id}" in md_res.text or run_id in md_res.text

    # 4. User isolation: foreign user returns 404
    other_client = TestClient(app, headers={"Authorization": f"Bearer {other_token}"})
    foreign_res = other_client.get(f"/api/v1/runs/{run_id}/report.pdf")
    assert foreign_res.status_code == 404
