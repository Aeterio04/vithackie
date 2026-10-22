"""Unit and integration tests for verifier.py."""

import json
import os
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from app.models import (
    Bug,
    BugsFile,
    Catalog,
    Evidence,
    Run,
    RunInput,
    Step,
    TestCase,
    Verification,
)
from app import runner_client
from app import storage
from app import verifier


def setup_test_run(run_id: str, tmp_path: Path) -> Path:
    storage.settings.runs_dir = tmp_path
    r_dir = storage.run_dir(run_id)

    run_input = RunInput(
        runId=run_id,
        createdAt="2026-10-18T00:00:00Z",
        targetUrl="http://localhost:4000",
        specRaw="S1: Test",
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
    return r_dir


def test_verify_bug_confirmed(tmp_path, monkeypatch):
    run_id = "test-verify-confirmed"
    setup_test_run(run_id, tmp_path)

    err_msg = "Error: expect(received).toBe(expected)\nExpected: true\nReceived: false"
    err_sig = runner_client.signature(err_msg)

    bug = Bug(
        id="B01",
        testId="T01",
        source="planned",
        title="T01: Bug test",
        grep="T01:",
        file="scripts/T01.spec.ts",
        category="other",
        severity="medium",
        specRef=["S1"],
        steps=["Step 1"],
        expected="true",
        actual="false",
        errorMessage=err_msg,
        signature=err_sig,
        duplicates=[],
        evidence=Evidence(),
        status="candidate",
    )
    storage.save_model(run_id, "bugs.json", BugsFile(runId=run_id, bugs=[bug]))

    # Mock run_playwright and parse_report to simulate 3 identical failures
    mock_raw = runner_client.RawRun(
        exit_code=1,
        report_path="/tmp/fake_report.json",
        stdout="failed",
        stderr="",
        duration_s=0.5,
    )
    mock_records = [
        {
            "title": "T01: Bug test",
            "file": "scripts/T01.spec.ts",
            "status": "failed",
            "durationMs": 500,
            "errorMessage": err_msg,
            "attachments": [],
        }
    ]

    monkeypatch.setattr(runner_client, "run_playwright", lambda *args, **kwargs: mock_raw)
    monkeypatch.setattr(runner_client, "parse_report", lambda *args, **kwargs: mock_records)

    v = verifier.verify_bug(run_id, "B01")
    assert v.status == "confirmed"
    assert v.reproduced == 3
    assert len(v.attempts) == 3
    for a in v.attempts:
        assert a.reproduced is True
        assert a.outcome == "assertion_failure"

    # Verify bugs.json updated
    updated_bugs = storage.load_model(run_id, "bugs.json", BugsFile)
    assert updated_bugs.bugs[0].status == "confirmed"
    assert updated_bugs.bugs[0].replay.reproduced == 3
    assert updated_bugs.bugs[0].replay.attempts == 3


def test_verify_bug_flaky(tmp_path, monkeypatch):
    run_id = "test-verify-flaky"
    setup_test_run(run_id, tmp_path)

    err_msg = "Error: expect(received).toBe(expected)\nExpected: true\nReceived: false"
    err_sig = runner_client.signature(err_msg)

    bug = Bug(
        id="B01",
        testId="T01",
        source="planned",
        title="T01: Flaky bug",
        grep="T01:",
        file="scripts/T01.spec.ts",
        category="other",
        severity="medium",
        specRef=["S1"],
        steps=["Step 1"],
        expected="true",
        actual="false",
        errorMessage=err_msg,
        signature=err_sig,
        duplicates=[],
        evidence=Evidence(),
        status="candidate",
    )
    storage.save_model(run_id, "bugs.json", BugsFile(runId=run_id, bugs=[bug]))

    # Attempt 1: fail, Attempt 2: pass, Attempt 3: fail (2/3 -> flaky)
    call_count = 0

    def mock_parse_report(path):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return [{"title": "T01: Flaky bug", "file": "scripts/T01.spec.ts", "status": "passed", "durationMs": 300, "errorMessage": "", "attachments": []}]
        return [{"title": "T01: Flaky bug", "file": "scripts/T01.spec.ts", "status": "failed", "durationMs": 500, "errorMessage": err_msg, "attachments": []}]

    mock_raw = runner_client.RawRun(exit_code=1, report_path="/tmp/fake.json", stdout="", stderr="", duration_s=0.5)
    monkeypatch.setattr(runner_client, "run_playwright", lambda *args, **kwargs: mock_raw)
    monkeypatch.setattr(runner_client, "parse_report", mock_parse_report)

    v = verifier.verify_bug(run_id, "B01")
    assert v.status == "flaky"
    assert v.reproduced == 2
    assert v.attempts[0].reproduced is True
    assert v.attempts[1].reproduced is False
    assert v.attempts[2].reproduced is True


def test_verify_bug_not_reproduced(tmp_path, monkeypatch):
    run_id = "test-verify-not-reproduced"
    setup_test_run(run_id, tmp_path)

    err_msg = "Error: expect(received).toBe(expected)\nExpected: true\nReceived: false"
    err_sig = runner_client.signature(err_msg)

    bug = Bug(
        id="B01",
        testId="T01",
        source="planned",
        title="T01: Not reproduced",
        grep="T01:",
        file="scripts/T01.spec.ts",
        category="other",
        severity="medium",
        specRef=["S1"],
        steps=["Step 1"],
        expected="true",
        actual="false",
        errorMessage=err_msg,
        signature=err_sig,
        duplicates=[],
        evidence=Evidence(),
        status="candidate",
    )
    storage.save_model(run_id, "bugs.json", BugsFile(runId=run_id, bugs=[bug]))

    # Passes all 3 times
    mock_records = [{"title": "T01: Not reproduced", "file": "scripts/T01.spec.ts", "status": "passed", "durationMs": 300, "errorMessage": "", "attachments": []}]
    mock_raw = runner_client.RawRun(exit_code=0, report_path="/tmp/fake.json", stdout="", stderr="", duration_s=0.3)
    monkeypatch.setattr(runner_client, "run_playwright", lambda *args, **kwargs: mock_raw)
    monkeypatch.setattr(runner_client, "parse_report", lambda *args, **kwargs: mock_records)

    v = verifier.verify_bug(run_id, "B01")
    assert v.status == "not_reproduced"
    assert v.reproduced == 0


def test_verify_bug_different_assertion_fails(tmp_path, monkeypatch):
    run_id = "test-verify-diff-assert"
    setup_test_run(run_id, tmp_path)

    orig_err = "Error: expect(received).toBe(expected)\nExpected: 100\nReceived: 50"
    diff_err = "Error: expect(locator).toBeVisible()\nReceived: hidden"

    bug = Bug(
        id="B01",
        testId="T01",
        source="planned",
        title="T01: Diff error",
        grep="T01:",
        file="scripts/T01.spec.ts",
        category="other",
        severity="medium",
        specRef=["S1"],
        steps=["Step 1"],
        expected="100",
        actual="50",
        errorMessage=orig_err,
        signature=runner_client.signature(orig_err),
        duplicates=[],
        evidence=Evidence(),
        status="candidate",
    )
    storage.save_model(run_id, "bugs.json", BugsFile(runId=run_id, bugs=[bug]))

    # Fails 3 times with diff_err
    mock_records = [{"title": "T01: Diff error", "file": "scripts/T01.spec.ts", "status": "failed", "durationMs": 400, "errorMessage": diff_err, "attachments": []}]
    mock_raw = runner_client.RawRun(exit_code=1, report_path="/tmp/fake.json", stdout="", stderr="", duration_s=0.4)
    monkeypatch.setattr(runner_client, "run_playwright", lambda *args, **kwargs: mock_raw)
    monkeypatch.setattr(runner_client, "parse_report", lambda *args, **kwargs: mock_records)

    v = verifier.verify_bug(run_id, "B01")
    assert v.status == "not_reproduced"
    assert v.reproduced == 0


def test_verify_bug_crash_fail_soft(tmp_path, monkeypatch):
    run_id = "test-verify-crash"
    setup_test_run(run_id, tmp_path)

    err_msg = "Error: expect(received).toBe(expected)\nExpected: true\nReceived: false"
    bug = Bug(
        id="B01",
        testId="T01",
        source="planned",
        title="T01: Crash test",
        grep="T01:",
        file="scripts/T01.spec.ts",
        category="other",
        severity="medium",
        specRef=["S1"],
        steps=["Step 1"],
        expected="true",
        actual="false",
        errorMessage=err_msg,
        signature=runner_client.signature(err_msg),
        duplicates=[],
        evidence=Evidence(),
        status="candidate",
    )
    storage.save_model(run_id, "bugs.json", BugsFile(runId=run_id, bugs=[bug]))

    # Attempt 2 crashes (exit_code -9 timeout)
    attempt = 0

    def mock_run_pw(*args, **kwargs):
        nonlocal attempt
        attempt += 1
        if attempt == 2:
            return runner_client.RawRun(exit_code=-9, report_path=None, stdout="", stderr="timeout", duration_s=10.0)
        return runner_client.RawRun(exit_code=1, report_path="/tmp/fake.json", stdout="", stderr="", duration_s=0.5)

    def mock_parse(path):
        return [{"title": "T01: Crash test", "file": "scripts/T01.spec.ts", "status": "failed", "durationMs": 500, "errorMessage": err_msg, "attachments": []}]

    monkeypatch.setattr(runner_client, "run_playwright", mock_run_pw)
    monkeypatch.setattr(runner_client, "parse_report", mock_parse)

    v = verifier.verify_bug(run_id, "B01")
    assert v.status == "flaky"
    assert v.reproduced == 2
    assert v.attempts[1].outcome == "test_error"
    assert v.attempts[1].reproduced is False


def test_verify_never_calls_reset(tmp_path, monkeypatch):
    """Verify that verifier never calls /__reset during replays."""
    run_id = "test-verify-no-reset"
    setup_test_run(run_id, tmp_path)

    err_msg = "Error: expect(received).toBe(expected)\nExpected: true\nReceived: false"
    bug = Bug(
        id="B01",
        testId="T01",
        source="planned",
        title="T01: No reset",
        grep="T01:",
        file="scripts/T01.spec.ts",
        category="other",
        severity="medium",
        specRef=["S1"],
        steps=["Step 1"],
        expected="true",
        actual="false",
        errorMessage=err_msg,
        signature=runner_client.signature(err_msg),
        duplicates=[],
        evidence=Evidence(),
        status="candidate",
    )
    storage.save_model(run_id, "bugs.json", BugsFile(runId=run_id, bugs=[bug]))

    # Spy on urllib and httpx or requests
    reset_called = False

    def check_url(url, *args, **kwargs):
        nonlocal reset_called
        if "__reset" in str(url):
            reset_called = True
        return MagicMock()

    mock_raw = runner_client.RawRun(exit_code=1, report_path="/tmp/fake.json", stdout="", stderr="", duration_s=0.5)
    mock_records = [{"title": "T01: No reset", "file": "scripts/T01.spec.ts", "status": "failed", "durationMs": 500, "errorMessage": err_msg, "attachments": []}]
    monkeypatch.setattr(runner_client, "run_playwright", lambda *args, **kwargs: mock_raw)
    monkeypatch.setattr(runner_client, "parse_report", lambda *args, **kwargs: mock_records)

    with patch("urllib.request.urlopen", side_effect=check_url):
        verifier.verify_bug(run_id, "B01")

    assert reset_called is False, "/__reset must never be called during verification"
