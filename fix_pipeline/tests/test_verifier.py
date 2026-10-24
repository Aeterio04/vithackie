"""Unit tests for VerifierAgent."""

import os
import pytest
from kawach_fix.agents.verifier import run_verifier
from kawach_fix.clients.runner import PlaywrightScriptRunner
from kawach_fix.schemas import FixOptions, FixRequest, RunItem
from tests.fakes import FakeRunner


@pytest.mark.asyncio
async def test_verifier_confirmed_verdict(sample_request: FixRequest):
    """When failures >= min_failures, verdict must be 'confirmed' and early_result is None."""
    sample_request.options.verify_runs = 3
    sample_request.options.min_failures = 2

    # 3 failing runs
    canned_runs = [
        RunItem(index=1, passed=False, error_text="Selector #add not found", duration_ms=100),
        RunItem(index=2, passed=False, error_text="Selector #add not found", duration_ms=110),
        RunItem(index=3, passed=True, duration_ms=90),
    ]
    runner = FakeRunner(outcomes=canned_runs)
    verification, early_result = await run_verifier(sample_request, runner)

    assert verification.verdict == "confirmed"
    assert verification.failures == 2
    assert verification.observed_error == "Selector #add not found"
    assert early_result is None
    assert runner.call_count == 3


@pytest.mark.asyncio
async def test_verifier_flaky_verdict(sample_request: FixRequest):
    """When 0 < failures < min_failures, verdict is 'flaky' and early_result is set."""
    sample_request.options.verify_runs = 3
    sample_request.options.min_failures = 2

    # 1 failure only (threshold is 2)
    canned_runs = [
        RunItem(index=1, passed=True, duration_ms=100),
        RunItem(index=2, passed=False, error_text="Intermittent timeout", duration_ms=200),
        RunItem(index=3, passed=True, duration_ms=100),
    ]
    runner = FakeRunner(outcomes=canned_runs)
    verification, early_result = await run_verifier(sample_request, runner)

    assert verification.verdict == "flaky"
    assert verification.failures == 1
    assert early_result is not None
    assert early_result.status == "flaky"
    assert "flaky" in early_result.reason.lower()


@pytest.mark.asyncio
async def test_verifier_not_reproduced_verdict(sample_request: FixRequest):
    """When 0 failures occur, verdict is 'not_reproduced' and early_result is set."""
    sample_request.options.verify_runs = 3
    sample_request.options.min_failures = 2

    canned_runs = [
        RunItem(index=1, passed=True, duration_ms=50),
        RunItem(index=2, passed=True, duration_ms=55),
        RunItem(index=3, passed=True, duration_ms=48),
    ]
    runner = FakeRunner(outcomes=canned_runs)
    verification, early_result = await run_verifier(sample_request, runner)

    assert verification.verdict == "not_reproduced"
    assert verification.failures == 0
    assert early_result is not None
    assert early_result.status == "not_reproduced"
    assert "does not exist" in early_result.reason


def test_subprocess_clean_environment():
    """Verify that PlaywrightScriptRunner builds a pristine environment free of tokens."""
    runner = PlaywrightScriptRunner()
    os.environ["SECRET_TOKEN"] = "ghp_supersecretvalue1234567890abcdef"
    os.environ["GITHUB_PAT"] = "github_pat_supersecrettoken1234567890"
    os.environ["GROQ_API_KEY"] = "gsk_supersecretgroqkey1234567890"

    clean_env = runner._build_clean_env("http://localhost:4000")

    assert "SECRET_TOKEN" not in clean_env
    assert "GITHUB_PAT" not in clean_env
    assert "GROQ_API_KEY" not in clean_env
    assert clean_env["BASE_URL"] == "http://localhost:4000"
    assert clean_env["CI"] == "1"
    # PATH should be preserved for node execution
    assert "PATH" in clean_env
