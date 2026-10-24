"""Unit tests for PRAgent."""

import pytest
from kawach_fix.agents.pr_raiser import build_pr_body, run_pr_raiser
from kawach_fix.schemas import (
    CommitContext,
    FileEdit,
    FilePatch,
    FixProposal,
    FixRequest,
    PullRequestInfo,
    VerificationResult,
)
from tests.fakes import FakeGitHub


@pytest.fixture
def dummy_verification() -> VerificationResult:
    return VerificationResult(
        runs=[],
        failures=3,
        verdict="confirmed",
        observed_error="Expected count 1, received 0",
    )


@pytest.fixture
def dummy_commit_context() -> CommitContext:
    return CommitContext(
        sha="9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b",
        message="refactor: counter state handling",
        author="Dev Developer",
        files=[
            FilePatch(
                path="src/components/Counter.tsx",
                status="modified",
                patch="@@ -10,3 +10,3 @@",
                content_at_sha="function Counter() { setCount(c => c); }",
                blob_sha="blob123",
            )
        ],
    )


@pytest.fixture
def dummy_proposal() -> FixProposal:
    return FixProposal(
        can_fix=True,
        confidence=0.95,
        root_cause="Incorrect state setter expression",
        explanation="Restored increment logic c + 1",
        edits=[
            FileEdit(
                path="src/components/Counter.tsx",
                old_str="setCount(c => c);",
                new_str="setCount(c => c + 1);",
            )
        ],
        pr_title="fix(kawach): fix counter increment",
        pr_summary="Restores proper state increment.",
    )


@pytest.mark.asyncio
async def test_pr_raiser_call_sequence_and_creation(
    sample_request: FixRequest,
    dummy_verification: VerificationResult,
    dummy_commit_context: CommitContext,
    dummy_proposal: FixProposal,
):
    """Ensure branch creation, file update, and pull request creation succeed."""
    gh = FakeGitHub(
        files={"src/components/Counter.tsx": ("function Counter() { setCount(c => c); }", "blob123")}
    )

    pr_info, result = await run_pr_raiser(
        sample_request, gh, dummy_verification, dummy_commit_context, dummy_proposal
    )

    assert result.status == "pr_opened"
    assert pr_info is not None
    assert pr_info.number == 1
    assert pr_info.branch == "kawach/fix-9a8b7c6"
    assert pr_info.created is True

    # Check updated content in fake
    updated_text, _ = await gh.get_file_content(sample_request.repo, "src/components/Counter.tsx", "ref")
    assert "setCount(c => c + 1);" in updated_text


@pytest.mark.asyncio
async def test_pr_raiser_idempotent_existing_pr(
    sample_request: FixRequest,
    dummy_verification: VerificationResult,
    dummy_commit_context: CommitContext,
    dummy_proposal: FixProposal,
):
    """When an open PR for kawach/fix-<sha7> already exists, return pr_exists."""
    existing_pr = PullRequestInfo(
        number=42,
        url="https://github.com/owner/example-repo/pull/42",
        branch="kawach/fix-9a8b7c6",
        created=False,
    )
    gh = FakeGitHub(existing_prs=[existing_pr])

    pr_info, result = await run_pr_raiser(
        sample_request, gh, dummy_verification, dummy_commit_context, dummy_proposal
    )

    assert result.status == "pr_exists"
    assert result.pull_request is not None
    assert result.pull_request.number == 42
    assert "already exists" in result.reason
    # Zero write calls should have been made
    assert len(gh.updated_files) == 0


@pytest.mark.asyncio
async def test_pr_raiser_dry_run_makes_zero_writes(
    sample_request: FixRequest,
    dummy_verification: VerificationResult,
    dummy_commit_context: CommitContext,
    dummy_proposal: FixProposal,
):
    """When dry_run=True, make zero write operations and return dry_run_ready."""
    sample_request.options.dry_run = True
    gh = FakeGitHub()

    pr_info, result = await run_pr_raiser(
        sample_request, gh, dummy_verification, dummy_commit_context, dummy_proposal
    )

    assert result.status == "dry_run_ready"
    assert len(gh.updated_files) == 0
    assert len(gh.created_refs) == 0
    assert len(gh.prs) == 0
    assert "Zero GitHub writes performed" in result.reason


def test_build_pr_body_structured_fields(
    sample_request: FixRequest,
    dummy_verification: VerificationResult,
    dummy_commit_context: CommitContext,
    dummy_proposal: FixProposal,
):
    """Check that PR body includes all structured fields and footer."""
    body = build_pr_body(sample_request, dummy_verification, dummy_commit_context, dummy_proposal)

    assert sample_request.error.test_name in body
    assert "3/3 failures confirmed" in body
    assert dummy_commit_context.sha[:7] in body
    assert dummy_proposal.root_cause in body
    assert dummy_proposal.explanation in body
    assert "Confidence Score: 95%" in body
    assert "src/components/Counter.tsx" in body
    assert "Generated autonomously by Kawach GitHub Fix Pipeline" in body
