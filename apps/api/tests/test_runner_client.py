"""Unit and integration tests for runner_client.py."""

import json
import os
from pathlib import Path
import pytest
from unittest.mock import patch

from app.models import (
    Bug,
    Catalog,
    Results,
    Run,
    RunInput,
    Step,
    TestCase,
)
from app import runner_client
from app import storage


def test_is_assertion_failure():
    assert runner_client.is_assertion_failure("Error: expect(locator).toBeVisible() failed ...") is True
    assert runner_client.is_assertion_failure("Error: expect(received).toBe(expected) // Object.is equality") is True
    assert runner_client.is_assertion_failure("Test timeout of 30000ms exceeded.\n Error: expect(locator)...") is False
    assert runner_client.is_assertion_failure("Error: locator.click: Timeout 8000ms exceeded.") is False
    assert runner_client.is_assertion_failure("SyntaxError: Unexpected token") is False
    assert runner_client.is_assertion_failure("TypeError: Cannot read properties of undefined") is False


def test_is_assertion_failure_with_ansi_codes():
    ansi_prefix = "\x1b[31m"
    ansi_suffix = "\x1b[39m"

    assert runner_client.is_assertion_failure(f"{ansi_prefix}Error: expect(locator).toBeVisible() failed ...{ansi_suffix}") is True
    assert runner_client.is_assertion_failure(f"{ansi_prefix}Test timeout of 30000ms exceeded.\n Error: expect(locator)...{ansi_suffix}") is False
    assert runner_client.is_assertion_failure(f"{ansi_prefix}Error: locator.click: Timeout 8000ms exceeded.{ansi_suffix}") is False


def test_signature_uniqueness_and_normalization():
    msg1 = "Error: expect(received).toBe(expected)\nReceived: user-1729281234567-abcd\nExpected: 2026"
    msg2 = "Error: expect(received).toBe(expected)\nReceived: user-1729289999999-wxyz\nExpected: 9999"

    sig1 = runner_client.signature(msg1)
    sig2 = runner_client.signature(msg2)
    assert sig1 == sig2, "Different timestamps/unique ids should yield same signature"

    diff_matcher_msg = "Error: expect(locator).toBeVisible()\nReceived: not visible"
    sig3 = runner_client.signature(diff_matcher_msg)
    assert sig1 != sig3, "Different assertion messages must yield different signatures"


def test_triage_and_deduplication(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.settings, "runs_dir", tmp_path)
    run_id = "test-triage-run"
    r_dir = storage.run_dir(run_id)

    # Setup catalog
    t1 = TestCase(
        id="T01",
        title="T01: Signup validation",
        description="Check email format",
        specRef=["S2"],
        steps=[Step(n=1, action="Enter bad email", expected="Enter a valid email address")],
    )
    t2 = TestCase(
        id="T02",
        title="T02: Duplicate signup validation",
        description="Check bad email again",
        specRef=["S2"],
        steps=[Step(n=1, action="Enter bad email again", expected="Enter a valid email address")],
    )
    t3 = TestCase(
        id="T03",
        title="T03: Different failure",
        description="Check different thing",
        specRef=["S3"],
        steps=[Step(n=1, action="Enter short password", expected="Password must be at least 8 characters")],
    )
    catalog = Catalog(runId=run_id, generatedAt="2026-10-18T00:00:00Z", tests=[t1, t2, t3])
    storage.save_model(run_id, "catalog.json", catalog)

    # Setup fake results
    # T01 and T02 have identical error signature
    msg_dup1 = "Error: expect(received).toBe(expected)\nReceived: user-1729281111111-aaaa"
    msg_dup2 = "Error: expect(received).toBe(expected)\nReceived: user-1729282222222-bbbb"
    msg_diff = "Error: expect(locator).toHaveText(expected)\nReceived: short"

    results = Results(
        runId=run_id,
        startedAt="2026-10-18T00:00:00Z",
        durationSeconds=5.0,
        workers=2,
        tests=[
            runner_client.TestResult(
                testId="T01",
                title="T01: Signup validation",
                file="scripts/T01.spec.ts",
                source="planned",
                outcome="assertion_failure",
                durationMs=500,
                errorMessage=msg_dup1,
            ),
            runner_client.TestResult(
                testId="T02",
                title="T02: Duplicate signup validation",
                file="scripts/T02.spec.ts",
                source="planned",
                outcome="assertion_failure",
                durationMs=600,
                errorMessage=msg_dup2,
            ),
            runner_client.TestResult(
                testId="T03",
                title="T03: Different failure",
                file="scripts/T03.spec.ts",
                source="planned",
                outcome="assertion_failure",
                durationMs=700,
                errorMessage=msg_diff,
            ),
            runner_client.TestResult(
                testId="T04",
                title="T04: Passing test",
                file="scripts/T04.spec.ts",
                source="planned",
                outcome="passed",
                durationMs=400,
            ),
            runner_client.TestResult(
                testId="T05",
                title="T05: Test error",
                file="scripts/T05.spec.ts",
                source="planned",
                outcome="test_error",
                durationMs=2000,
                errorMessage="Timeout 2000ms exceeded",
            ),
        ],
    )
    storage.save_model(run_id, "results.json", results)

    bugs = runner_client.triage(run_id)
    # T01 and T02 merged into 1 bug, T03 is 2nd bug -> 2 total bugs
    assert len(bugs) == 2
    assert bugs[0].id == "B01"
    assert bugs[0].testId == "T01"
    assert bugs[0].duplicates == ["T02"]
    assert bugs[1].id == "B02"
    assert bugs[1].testId == "T03"
    assert bugs[1].duplicates == []


@pytest.mark.integration
def test_real_hand_written_runner_integration(monkeypatch):
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run real Playwright integration test")

    run_id = "_test_integration"
    r_dir = storage.run_dir(run_id)

    # Set up input and run models
    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        targetUrl="http://localhost:4000",
        specRaw="S1: Test",
        username="qa.tester@example.com",
    )
    storage.save_model(run_id, "input.json", run_input)
    storage.save_model(
        run_id,
        "run.json",
        Run(
            runId=run_id,
            createdAt="2026-10-18T00:00:00Z",
            updatedAt="2026-10-18T00:00:00Z",
            targetUrl="http://localhost:4000",
        ),
    )

    # Copy hand-written specs to run_dir/scripts
    scripts_dir = r_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    src_hand_written = storage.settings.repo_root / "apps" / "runner" / "hand-written"

    # Adapt relative imports for scripts/ directory (../../../apps/runner/fixtures)
    for spec_file in src_hand_written.glob("*.spec.ts"):
        content = spec_file.read_text(encoding="utf-8")
        adapted = content.replace("'../fixtures'", "'../../../apps/runner/fixtures'")
        (scripts_dir / spec_file.name).write_text(adapted, encoding="utf-8")

    # Set catalog
    catalog = Catalog(
        runId=run_id,
        generatedAt="2026-10-18T00:00:00Z",
        tests=[
            TestCase(id="T90", title="T90: Login page shows the Log in heading", description="T90", specRef=["S4"], status="approved"),
            TestCase(id="T91", title="T91: Deliberate assertion failure", description="T91", specRef=["S4"], status="approved"),
            TestCase(id="T92", title="T92: Deliberate test error", description="T92", specRef=["S4"], status="approved"),
            TestCase(id="T93", title="T93: Off-domain request is blocked", description="T93", specRef=["S4"], status="approved"),
        ],
    )
    storage.save_model(run_id, "catalog.json", catalog)

    results = runner_client.run_tests(run_id, workers=2)
    assert results.summary.passed == 2  # T90, T93
    assert results.summary.assertionFailures == 1  # T91
    assert results.summary.testErrors == 1  # T92

    # Evidence check
    ev_t91 = r_dir / "evidence" / "T91"
    assert (ev_t91 / "screenshot.png").exists()
    assert (ev_t91 / "video.webm").exists()
    assert (ev_t91 / "trace.zip").exists()
    assert (ev_t91 / "console.json").exists()
    assert (ev_t91 / "network.json").exists()

    bugs = runner_client.triage(run_id)
    assert len(bugs) == 1
    assert bugs[0].testId == "T91"
