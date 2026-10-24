"""Tests ensuring secrets and PATs are scrubbed from outputs and logs."""

import json
import logging
from pathlib import Path
import pytest
from pydantic import SecretStr

from kawach_fix.deps import Deps
from kawach_fix.graph import arun_fix_pipeline
from kawach_fix.redact import RedactingLoggingFilter, redact_text
from kawach_fix.schemas import FixRequest, RunItem
from tests.fakes import FakeGitHub, FakeLLM, FakeRunner


def test_redact_token_patterns():
    """Verify various token formats are scrubbed."""
    raw = (
        "Logs: ghp_111122223333444455556666777788889999\n"
        "PAT: github_pat_11AAAAAA0000000000000000000000000000000000000000000000000000000000\n"
        "Groq: gsk_abcdef1234567890abcdef1234567890\n"
        "Bearer: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\n"
    )
    redacted = redact_text(raw)
    assert "ghp_" not in redacted
    assert "github_pat_" not in redacted
    assert "gsk_" not in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_logging_filter_scrubs_secrets(caplog):
    """Verify RedactingLoggingFilter prevents secrets from being recorded."""
    logger = logging.getLogger("test_redaction_logger")
    logger.setLevel(logging.INFO)
    logger.addFilter(RedactingLoggingFilter(extra_secrets=["custom_super_secret_pat"]))

    with caplog.at_level(logging.INFO):
        logger.info("Connecting using custom_super_secret_pat and ghp_123456789012345678901234567890123456")

    assert "custom_super_secret_pat" not in caplog.text
    assert "ghp_123456789012345678901234567890123456" not in caplog.text
    assert "[REDACTED_SECRET]" in caplog.text


@pytest.mark.asyncio
async def test_secrets_never_leak_in_graph_outputs_or_artifacts(
    sample_request: FixRequest,
    sample_proposal_json: str,
    tmp_path: Path,
):
    """End-to-end audit: PAT never appears in FixResult, artifacts, or LLM prompts."""
    raw_pat = "github_pat_11AAAAAA0000000000000000000000000000000000000000000000000000000000"
    sample_request.github_pat = SecretStr(raw_pat)

    failing_runner = FakeRunner(outcomes=[
        RunItem(index=1, passed=False, error_text="Error", duration_ms=100),
        RunItem(index=2, passed=False, error_text="Error", duration_ms=100),
        RunItem(index=3, passed=False, error_text="Error", duration_ms=100),
    ])
    fake_github = FakeGitHub()
    fake_llm = FakeLLM(responses=[sample_proposal_json])

    runs_dir = tmp_path / "fix_runs"
    deps = Deps(
        runner=failing_runner,
        github=fake_github,
        llm=fake_llm,
        runs_dir=runs_dir,
    )

    result = await arun_fix_pipeline(sample_request, deps)

    # 1. Assert PAT never in FixResult json serialization
    result_json = result.model_dump_json()
    assert raw_pat not in result_json

    # 2. Assert PAT never in LLM prompt calls
    for call in fake_llm.recorded_calls:
        assert raw_pat not in call["system_prompt"]
        assert raw_pat not in call["user_prompt"]

    # 3. Assert PAT never in any artifact file on disk
    subdirs = list(runs_dir.iterdir())
    assert len(subdirs) == 1
    run_dir = subdirs[0]

    for artifact_file in run_dir.glob("*.json"):
        text_content = artifact_file.read_text(encoding="utf-8")
        assert raw_pat not in text_content, f"Secret leaked in artifact {artifact_file.name}!"
