"""End-to-end integration tests for LangGraph state machine."""

import json
from pathlib import Path
import pytest

from kawach_fix.clients.github import GitHubClientError
from kawach_fix.deps import Deps
from kawach_fix.graph import arun_fix_pipeline, run_fix_pipeline
from kawach_fix.schemas import FixRequest, RunItem
from tests.fakes import FakeGitHub, FakeLLM, FakeRunner


@pytest.fixture
def failing_runner() -> FakeRunner:
    """Runner returning consistent failures to confirm test defect."""
    canned = [
        RunItem(index=1, passed=False, error_text="Selector #add not found", duration_ms=100),
        RunItem(index=2, passed=False, error_text="Selector #add not found", duration_ms=100),
        RunItem(index=3, passed=False, error_text="Selector #add not found", duration_ms=100),
    ]
    return FakeRunner(outcomes=canned)


@pytest.mark.asyncio
async def test_graph_happy_path_pr_opened(
    sample_request: FixRequest,
    failing_runner: FakeRunner,
    fake_github: FakeGitHub,
    sample_proposal_json: str,
    tmp_path: Path,
):
    """End-to-end happy path: verify -> collect -> propose -> raise_pr -> pr_opened."""
    deps = Deps(
        runner=failing_runner,
        github=fake_github,
        llm=FakeLLM(responses=[sample_proposal_json]),
        runs_dir=tmp_path / "fix_runs",
    )

    result = await arun_fix_pipeline(sample_request, deps)

    assert result.status == "pr_opened"
    assert result.pull_request is not None
    assert result.pull_request.number == 1
    assert result.verification is not None
    assert result.verification.verdict == "confirmed"
    assert result.commit is not None
    assert result.proposal is not None

    # Check generated artifacts
    runs_dir = tmp_path / "fix_runs"
    subdirs = list(runs_dir.iterdir())
    assert len(subdirs) == 1
    run_dir = subdirs[0]
    assert (run_dir / "verification.json").exists()
    assert (run_dir / "commit_context.json").exists()
    assert (run_dir / "llm_request_redacted.json").exists()
    assert (run_dir / "llm_response.json").exists()
    assert (run_dir / "result.json").exists()


@pytest.mark.asyncio
async def test_graph_exit_not_reproduced(
    sample_request: FixRequest,
    fake_github: FakeGitHub,
    fake_llm: FakeLLM,
    tmp_path: Path,
):
    """When test passes on verify, graph exits early at verify stage with not_reproduced."""
    passing_runner = FakeRunner(outcomes=[
        RunItem(index=1, passed=True, duration_ms=50),
        RunItem(index=2, passed=True, duration_ms=50),
        RunItem(index=3, passed=True, duration_ms=50),
    ])
    deps = Deps(
        runner=passing_runner,
        github=fake_github,
        llm=fake_llm,
        runs_dir=tmp_path / "fix_runs",
    )

    result = await arun_fix_pipeline(sample_request, deps)

    assert result.status == "not_reproduced"
    # Ensure collector and subsequent nodes were never invoked
    assert len(fake_github.recorded_calls) == 0
    assert fake_llm.call_count == 0


@pytest.mark.asyncio
async def test_graph_exit_no_editable_changes(
    sample_request: FixRequest,
    failing_runner: FakeRunner,
    fake_llm: FakeLLM,
    tmp_path: Path,
):
    """When latest commit has only lockfiles/binaries, graph exits at collect stage."""
    gh = FakeGitHub(
        latest_commit={
            "sha": "9999999999999999999999999999999999999999",
            "message": "chore: bump lock",
            "author": "Bot",
            "files": [{"filename": "package-lock.json", "status": "modified", "patch": "@@ -1 +1 @@"}],
        }
    )
    deps = Deps(
        runner=failing_runner,
        github=gh,
        llm=fake_llm,
        runs_dir=tmp_path / "fix_runs",
    )

    result = await arun_fix_pipeline(sample_request, deps)

    assert result.status == "no_editable_changes"
    assert fake_llm.call_count == 0


@pytest.mark.asyncio
async def test_graph_exit_github_error(
    sample_request: FixRequest,
    failing_runner: FakeRunner,
    fake_llm: FakeLLM,
    tmp_path: Path,
):
    """When GitHub API fails at collector, graph exits with github_error."""
    gh = FakeGitHub(error_to_raise=GitHubClientError(404, "Not Found"))
    deps = Deps(
        runner=failing_runner,
        github=gh,
        llm=fake_llm,
        runs_dir=tmp_path / "fix_runs",
    )

    result = await arun_fix_pipeline(sample_request, deps)

    assert result.status == "github_error"
    assert "404 Not Found" in result.reason
    assert fake_llm.call_count == 0


@pytest.mark.asyncio
async def test_graph_exit_fix_not_possible(
    sample_request: FixRequest,
    failing_runner: FakeRunner,
    fake_github: FakeGitHub,
    tmp_path: Path,
):
    """When LLM returns can_fix=False, graph exits with fix_not_possible."""
    llm = FakeLLM(responses=[json.dumps({
        "can_fix": False,
        "confidence": 0.1,
        "root_cause": "Database schema mismatch",
        "explanation": "Cannot be repaired in frontend component",
        "edits": [],
        "pr_title": "",
        "pr_summary": "",
    })])
    deps = Deps(
        runner=failing_runner,
        github=fake_github,
        llm=llm,
        runs_dir=tmp_path / "fix_runs",
    )

    result = await arun_fix_pipeline(sample_request, deps)

    assert result.status == "fix_not_possible"
    assert "Database schema mismatch" in result.reason
    assert len(fake_github.updated_files) == 0


@pytest.mark.asyncio
async def test_graph_exit_dry_run_ready(
    sample_request: FixRequest,
    failing_runner: FakeRunner,
    fake_github: FakeGitHub,
    sample_proposal_json: str,
    tmp_path: Path,
):
    """When dry_run=True, graph runs through propose and exits at raise_pr with dry_run_ready."""
    sample_request.options.dry_run = True
    deps = Deps(
        runner=failing_runner,
        github=fake_github,
        llm=FakeLLM(responses=[sample_proposal_json]),
        runs_dir=tmp_path / "fix_runs",
    )

    result = await arun_fix_pipeline(sample_request, deps)

    assert result.status == "dry_run_ready"
    assert len(fake_github.updated_files) == 0
    assert len(fake_github.prs) == 0


def test_sync_run_fix_pipeline_wrapper(
    sample_request: FixRequest,
    failing_runner: FakeRunner,
    fake_github: FakeGitHub,
    sample_proposal_json: str,
    tmp_path: Path,
):
    """Ensure synchronous run_fix_pipeline wrapper works correctly."""
    deps = Deps(
        runner=failing_runner,
        github=fake_github,
        llm=FakeLLM(responses=[sample_proposal_json]),
        runs_dir=tmp_path / "fix_runs",
    )
    result = run_fix_pipeline(sample_request, deps)
    assert result.status == "pr_opened"
