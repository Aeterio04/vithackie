import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from kawach.core.target_fetch import (
    validate_ip_ssrf,
    resolve_and_check_ssrf,
    get_shared_target_headers,
)
from kawach.execution.circuit_breaker import generate_owner_guidance
from kawach.execution.report_generator import _render_markdown
from kawach.schemas import Metrics


def test_target_fetch_blocks_cloud_metadata():
    ok, reason = validate_ip_ssrf("169.254.169.254", is_dev_allowed=True)
    assert not ok
    assert "cloud-metadata" in reason or "link-local" in reason

    ok6, reason6 = validate_ip_ssrf("fe80::1", is_dev_allowed=True)
    assert not ok6


def test_target_fetch_dns_failure():
    # Non-existent domain
    res = resolve_and_check_ssrf("this-domain-definitely-does-not-exist-123456789.org")
    assert not res.allowed
    assert "DNS" in (res.reason or "") or "getaddrinfo" in (res.reason or "")


def test_target_fetch_chrome_headers():
    headers = get_shared_target_headers()
    assert "User-Agent" in headers
    assert "Chrome/124" in headers["User-Agent"]
    assert "text/html" in headers["Accept"]


def test_circuit_breaker_guidance_generation():
    guidance = generate_owner_guidance("blocked_by_waf", "https://example.com", qa_token="test_token_123")
    assert "Site Owner Guidance" in guidance
    assert "https://example.com" in guidance
    assert "test_token_123" in guidance
    assert "X-QA-Token" in guidance


def test_report_generator_environment_barrier_banner(tmp_path):
    metrics = Metrics(runId="test_env_run", wallClockSeconds=4.5)
    env_issue = {
        "classification": "dns_failure",
        "origin": "target",
        "reason": "DNS resolution failed: [Errno 11001] getaddrinfo failed",
        "guidance": "1. Verify domain registration. 2. Verify DNS A/AAAA records.",
    }
    
    data = {
        "run_id": "test_env_run",
        "run": MagicMock(targetUrl="https://motionpremios.com", mode="manual", stage="done_with_environment_issue", createdAt="2026-10-25T00:00:00Z"),
        "run_input": None,
        "catalog": None,
        "results": None,
        "bugs_file": None,
        "app_map": None,
        "review_log": None,
        "metrics": metrics,
        "run_folder": tmp_path,
        "spec_items": [],
        "test_scripts": {},
        "repro_scripts": {},
        "verifications": {},
        "env_issue": env_issue,
    }
    
    report_md = _render_markdown(data)
    
    assert "Environment Barrier Detected" in report_md
    assert "motionpremios.com" in report_md
    assert "Site Owner Guidance" in report_md
    assert "1. Verify domain registration" in report_md
