"""Tests for Task A4: Executor, Exploratory Tester, Repro Writer, and Verifier."""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from kawach.core.config import settings
from kawach.execution.exploratory import (
    ExploratoryTester,
    emit_minimal_repro_script,
    shrink_failing_path,
)
from kawach.execution.runner import is_infrastructure_flake, parse_report
from kawach.execution.triage import triage
from kawach.execution.verifier import verify_bug
from kawach.schemas import (
    AppMap,
    Bug,
    BugsFile,
    Catalog,
    Evidence,
    FrontierState,
    Journey,
    Results,
    ResultsSummary,
    Run,
    RunInput,
    StateNode,
    Step,
    TestCase,
    TestResult as SingleTestResult,
)
from kawach.storage import artifacts as storage


def test_parse_report_checkpoint_telemetry(tmp_path):
    """Verify that parse_report walks step hierarchy and captures checkpoint failure telemetry."""
    report_data = {
        "suites": [
            {
                "title": "T01 Suite",
                "file": "scripts/T01.spec.ts",
                "specs": [
                    {
                        "title": "T01: Multi-step checkout flow",
                        "file": "scripts/T01.spec.ts",
                        "tests": [
                            {
                                "results": [
                                    {
                                        "status": "failed",
                                        "duration": 4200,
                                        "errors": [{"message": "Error: expect(locator).toBeVisible()\nCall log:\n- waiting for locator('button.submit')"}],
                                        "steps": [
                                            {"title": "Step 1: Navigate to /checkout", "duration": 500, "error": None},
                                            {"title": "Step 2: Fill billing address", "duration": 1200, "error": None},
                                            {
                                                "title": "Step 3: Submit order button visible",
                                                "duration": 2500,
                                                "error": {"message": "expect(locator).toBeVisible() failed"},
                                            },
                                        ],
                                        "attachments": [],
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        ]
    }
    report_file = tmp_path / "playwright-report.json"
    report_file.write_text(json.dumps(report_data), encoding="utf-8")

    records = parse_report(str(report_file))
    assert len(records) == 1
    rec = records[0]
    assert rec["title"] == "T01: Multi-step checkout flow"
    assert rec["status"] == "failed"
    assert rec["failedStep"] == 3
    assert rec["totalSteps"] == 3
    assert rec["checkpoint"] == "Step 3: Submit order button visible"


def test_infrastructure_flake_gating():
    """Verify that is_infrastructure_flake detects network/runner failures and strictly excludes assertions."""
    # Infrastructure flakes
    assert is_infrastructure_flake("page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:4000")
    assert is_infrastructure_flake("Worker process exited unexpectedly: Target closed")
    assert is_infrastructure_flake("browser.newContext: Browser has been closed")
    assert is_infrastructure_flake("Navigation timeout of 30000ms exceeded")
    assert is_infrastructure_flake("FetchError: request to http://localhost:4000 failed, reason: socket hang up")

    # Assertion failures must NEVER be treated as infrastructure flakes
    assert not is_infrastructure_flake("Error: expect(locator).toBeVisible()\nReceived: false\nExpected: true")
    assert not is_infrastructure_flake("Error: expect(received).toEqual(expected) // Object.is equality")
    assert not is_infrastructure_flake("expect(page.locator('h1')).toHaveText('Dashboard')")
    assert not is_infrastructure_flake("")
    assert not is_infrastructure_flake(None)


def test_exploratory_tester_mutations_and_specs(tmp_path):
    """Verify that ExploratoryTester derives mutations from deepest frontier states and generates valid specs."""
    app_map = AppMap(
        runId="test-exp-01",
        baseUrl="http://localhost:4000",
        generatedAt="2026-10-23T00:00:00Z",
        states=[
            StateNode(stateId="state_root", url="http://localhost:4000/", depth=0, title="Home"),
            StateNode(stateId="state_catalog", url="http://localhost:4000/catalog", depth=1, title="Catalog"),
            StateNode(stateId="state_wizard", url="http://localhost:4000/wizard/step-2", depth=3, title="Deep Wizard"),
        ],
        transitions=[],
        unexploredFrontier=[
            FrontierState(stateId="frontier_l1", url="http://localhost:4000/search", depth=1, reason="Unclicked filters"),
            FrontierState(stateId="frontier_l3", url="http://localhost:4000/admin/settings/security", depth=3, reason="Unexplored tab"),
            FrontierState(stateId="frontier_l2", url="http://localhost:4000/cart/shipping", depth=2, reason="Secondary form"),
        ],
        journeys=[
            Journey(
                journeyId="J01",
                title="Add to cart and checkout flow",
                depth=3,
                steps=[
                    "Navigate to /catalog",
                    "Click [data-testid=add-to-cart]",
                    "Click [data-testid=checkout]",
                    "Fill address form",
                ],
            )
        ],
    )

    tester = ExploratoryTester(run_id="test-exp-01", budget_tests=4)
    exploratory_tests = tester.plan_exploratory_tests(app_map)

    assert len(exploratory_tests) <= 4
    assert all(t.id.startswith("X") for t in exploratory_tests)

    # Check that mutations include reorder, repeat/interrupt, and perturbation
    edge_tags = {tag for t in exploratory_tests for tag in t.edgeTags}
    assert any(tag in edge_tags for tag in ("order_permutations", "interrupted_flow", "rapid_repeat_submit"))

    # Perturbation candidates should target the deepest frontier state (frontier_l3 at depth 3) first
    perturb_cases = [t for t in exploratory_tests if "html_script_escaping" in t.edgeTags]
    if perturb_cases:
        assert perturb_cases[0].coverageRef == ["frontier_l3"]

    # Generate executable Playwright spec files
    scripts_dir = tmp_path / "scripts"
    generated_specs = tester.generate_exploratory_specs(
        exploratory_tests=exploratory_tests,
        target_url="http://localhost:4000",
        scripts_dir=scripts_dir,
    )
    assert len(generated_specs) == len(exploratory_tests)
    for spec_path in generated_specs:
        assert spec_path.exists()
        content = spec_path.read_text(encoding="utf-8")
        assert "from '../../../apps/runner/fixtures'" in content
        assert "test.describe(" in content
        assert "test(" in content


def test_path_shrinking_and_repro_writer(tmp_path):
    """Verify that shrink_failing_path discards post-failure actions and repro writer generates script."""
    full_path = [
        "Navigate to /login",
        "Fill input with 'admin'",
        "Fill password with 'secret'",
        "Click [data-testid=login-submit]",
        "Assert dashboard heading visible",  # Failed at step 5
        "Navigate to /settings",
        "Click delete account button",
    ]

    shrunk = shrink_failing_path(full_path, failed_step_index=5)
    assert len(shrunk) == 5
    assert shrunk[-1] == "Assert dashboard heading visible"
    assert "Navigate to /settings" not in shrunk

    repro_file = emit_minimal_repro_script(
        bug_id="B01",
        title="Dashboard heading failed to render after login",
        base_url="http://localhost:4000",
        steps=shrunk,
        out_dir=tmp_path / "repro",
    )

    assert repro_file.exists()
    content = repro_file.read_text(encoding="utf-8")
    assert "B01: Defect Reproduction" in content
    assert "page.goto" in content
    assert "page.locator" in content


def test_triage_deduplication_by_failing_state_and_signature(tmp_path, monkeypatch):
    """Verify that triage groups bugs by compound key (failing state, symptom signature)."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)

    run_id = "test-triage-run-001"
    r_dir = runs_dir / run_id
    r_dir.mkdir(parents=True, exist_ok=True)

    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-23T00:00:00Z",
        targetUrl="http://localhost:4000",
        prompt="Testing triage deduplication",
        specRaw="S1: Auth\nS2: Profile",
        spec=[],
    )
    storage.save_model(run_id, "input.json", run_input)

    catalog = Catalog(
        runId=run_id,
        generatedAt="2026-10-23T00:00:00Z",
        tests=[
            TestCase(
                id="T01",
                title="T01: Login submit button check",
                description="Checks login button",
                specRef=["S1"],
                priority="high",
                depth=1,
                category="single_step",
                coverageRef=["state_login"],
                steps=[
                    Step(n=1, action="Navigate to /login", checkpoint="Nav to login"),
                    Step(n=2, action="Click login submit", assertion="expect(locator).toBeVisible()", checkpoint="Assert submit visible"),
                ],
                status="approved",
            ),
            TestCase(
                id="T02",
                title="T02: Alternative login flow check",
                description="Checks same login button from alt route",
                specRef=["S1"],
                priority="medium",
                depth=1,
                category="single_step",
                coverageRef=["state_login"],
                steps=[
                    Step(n=1, action="Navigate to /login", checkpoint="Nav to login"),
                    Step(n=2, action="Click login submit", assertion="expect(locator).toBeVisible()", checkpoint="Assert submit visible"),
                ],
                status="approved",
            ),
            TestCase(
                id="T03",
                title="T03: Profile save button check",
                description="Checks profile save button",
                specRef=["S2"],
                priority="high",
                depth=2,
                category="deep_path",
                coverageRef=["state_profile"],
                steps=[
                    Step(n=1, action="Navigate to /profile", checkpoint="Nav to profile"),
                    Step(n=2, action="Click save profile", assertion="expect(locator).toBeVisible()", checkpoint="Assert save visible"),
                ],
                status="approved",
            ),
        ],
    )
    storage.save_model(run_id, "catalog.json", catalog)

    # Identical error message for all three tests
    err = "Error: expect(locator).toBeVisible()\nCall log:\n- locator resolved to null"

    results = Results(
        runId=run_id,
        startedAt="2026-10-23T00:00:00Z",
        durationSeconds=5.0,
        workers=2,
        tests=[
            SingleTestResult(
                testId="T01",
                title="T01: Login submit button check",
                file="scripts/T01.spec.ts",
                source="planned",
                outcome="assertion_failure",
                durationMs=1200,
                errorMessage=err,
                failedStep=2,
                totalSteps=2,
                depth=1,
                checkpoint="Assert submit visible",
            ),
            SingleTestResult(
                testId="T02",
                title="T02: Alternative login flow check",
                file="scripts/T02.spec.ts",
                source="planned",
                outcome="assertion_failure",
                durationMs=1100,
                errorMessage=err,
                failedStep=2,
                totalSteps=2,
                depth=1,
                checkpoint="Assert submit visible",
            ),
            SingleTestResult(
                testId="T03",
                title="T03: Profile save button check",
                file="scripts/T03.spec.ts",
                source="planned",
                outcome="assertion_failure",
                durationMs=1300,
                errorMessage=err,
                failedStep=2,
                totalSteps=2,
                depth=2,
                checkpoint="Assert save visible",
            ),
        ],
        summary=ResultsSummary(total=3, passed=0, assertionFailures=3, testErrors=0),
    )
    storage.save_model(run_id, "results.json", results)

    unique_bugs = triage(run_id)

    # T01 and T02 share same failing state (state_login) and error -> deduplicated into 1 bug
    # T03 has a different failing state (state_profile) -> preserved as distinct bug
    assert len(unique_bugs) == 2
    b01 = unique_bugs[0]
    b02 = unique_bugs[1]

    assert b01.id == "B01"
    assert b01.testId == "T01"
    assert "T02" in b01.duplicates

    assert b02.id == "B02"
    assert b02.testId == "T03"

    # Check reproduction scripts generated
    assert b01.reproductionScript is not None
    assert (r_dir / b01.reproductionScript).exists()


def test_llm_free_verifier_replays(tmp_path, monkeypatch):
    """Verify that verify_bug executes 3 deterministic replays without invoking LLM."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)

    run_id = "test-verify-run-001"
    r_dir = runs_dir / run_id
    r_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir = r_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "T01.spec.ts").write_text("// test script", encoding="utf-8")

    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-23T00:00:00Z",
        targetUrl="http://localhost:4000",
        prompt="Testing verifier replays",
        specRaw="S1: Auth",
        spec=[],
    )
    storage.save_model(run_id, "input.json", run_input)

    run_obj = Run(
        runId=run_id,
        createdAt="2026-10-23T00:00:00Z",
        updatedAt="2026-10-23T00:00:00Z",
        stage="verifying",
        targetUrl="http://localhost:4000",
    )
    storage.save_model(run_id, "run.json", run_obj)

    candidate_bug = Bug(
        id="B01",
        testId="T01",
        source="planned",
        title="T01: Button not visible",
        grep="T01:",
        file="scripts/T01.spec.ts",
        category="other",
        severity="medium",
        steps=["Step 1"],
        expected="Button visible",
        actual="expect(locator).toBeVisible() failed",
        errorMessage="Error: expect(locator).toBeVisible()\nlocator resolved to null",
        signature="state_login::sig12345",
        status="candidate",
    )
    storage.save_model(run_id, "bugs.json", BugsFile(runId=run_id, bugs=[candidate_bug]))

    # Mock raw run reports for 3 consecutive assertion failures
    mock_report = tmp_path / "mock_replay_report.json"
    mock_report.write_text(
        json.dumps({
            "suites": [{
                "title": "T01 Suite",
                "specs": [{
                    "title": "T01: Button not visible",
                    "tests": [{
                        "results": [{
                            "status": "failed",
                            "duration": 500,
                            "errors": [{"message": "Error: expect(locator).toBeVisible()\nlocator resolved to null"}],
                        }]
                    }]
                }]
            }]
        }),
        encoding="utf-8",
    )

    from kawach.execution.runner import RawRun
    mock_run_playwright = MagicMock(return_value=RawRun(
        exit_code=1,
        report_path=str(mock_report),
        stdout="",
        stderr="",
        duration_s=0.5,
    ))
    monkeypatch.setattr("kawach.execution.verifier.run_playwright", mock_run_playwright)

    verification = verify_bug(run_id, "B01")
    assert verification.bugId == "B01"
    assert verification.reproduced == 3
    assert verification.status == "confirmed"
    assert len(verification.attempts) == 3
    assert mock_run_playwright.call_count == 3
