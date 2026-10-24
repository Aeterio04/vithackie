"""Unit tests for GitHubCollectorAgent."""

import pytest
from kawach_fix.agents.github_collector import run_collector
from kawach_fix.clients.github import GitHubClientError
from kawach_fix.schemas import FixRequest, VerificationResult
from tests.fakes import FakeGitHub


@pytest.fixture
def dummy_verification() -> VerificationResult:
    return VerificationResult(
        runs=[],
        failures=2,
        verdict="confirmed",
        observed_error="Counter failed to increment",
    )


@pytest.mark.asyncio
async def test_collector_queries_only_main(sample_request: FixRequest, dummy_verification: VerificationResult):
    """Ensure collector fetches commit specifically for origin/main."""
    gh = FakeGitHub()
    commit_ctx, early_result = await run_collector(sample_request, gh, dummy_verification)

    assert commit_ctx is not None
    assert early_result is None
    assert commit_ctx.sha == "1234567890abcdef1234567890abcdef12345678"
    assert "get_latest_main_commit(owner/example-repo)" in gh.recorded_calls


@pytest.mark.asyncio
async def test_collector_skips_lockfiles_binary_and_removed(
    sample_request: FixRequest, dummy_verification: VerificationResult
):
    """Ensure package-lock.json, binaries, and deleted files are skipped with reason."""
    custom_commit = {
        "sha": "abcdef1234567890abcdef1234567890abcdef12",
        "message": "chore: updates",
        "author": "Alice",
        "files": [
            {
                "filename": "package-lock.json",
                "status": "modified",
                "patch": "@@ -1 +1 @@",
            },
            {
                "filename": "icon.png",
                "status": "modified",
                "patch": None,
            },
            {
                "filename": "old_module.ts",
                "status": "removed",
                "patch": "@@ -1 +0 @@",
            },
            {
                "filename": "src/App.tsx",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n- old\n+ new",
            },
        ],
    }
    gh = FakeGitHub(
        latest_commit=custom_commit,
        files={"src/App.tsx": ("export const App = () => <div>Hello</div>;", "blob_sha_app")},
    )

    commit_ctx, early_result = await run_collector(sample_request, gh, dummy_verification)

    assert early_result is None
    assert commit_ctx is not None
    assert len(commit_ctx.files) == 1
    assert commit_ctx.files[0].path == "src/App.tsx"

    skipped_map = {s.path: s.reason for s in commit_ctx.skipped}
    assert "package-lock.json" in skipped_map
    assert "icon.png" in skipped_map
    assert "old_module.ts" in skipped_map
    assert "deleted" in skipped_map["old_module.ts"].lower()


@pytest.mark.asyncio
async def test_collector_truncates_large_patch(sample_request: FixRequest, dummy_verification: VerificationResult):
    """Ensure patch exceeding max_patch_chars is truncated with truncated=True."""
    sample_request.options.max_patch_chars = 100
    huge_patch = "A" * 500

    custom_commit = {
        "sha": "sha_huge_patch",
        "message": "large diff",
        "author": "Bob",
        "files": [
            {
                "filename": "src/Large.ts",
                "status": "modified",
                "patch": huge_patch,
            }
        ],
    }
    gh = FakeGitHub(
        latest_commit=custom_commit,
        files={"src/Large.ts": ("const content = 1;", "blob_sha_large")},
    )

    commit_ctx, early_result = await run_collector(sample_request, gh, dummy_verification)
    assert early_result is None
    assert commit_ctx is not None
    assert len(commit_ctx.files) == 1
    file_patch = commit_ctx.files[0]
    assert file_patch.truncated is True
    assert len(file_patch.patch) == 100


@pytest.mark.asyncio
async def test_collector_no_editable_changes(sample_request: FixRequest, dummy_verification: VerificationResult):
    """When all files are lockfiles/binary/removed, exit with no_editable_changes."""
    custom_commit = {
        "sha": "sha_only_lockfiles",
        "message": "chore: bump lockfile",
        "author": "Bob",
        "files": [
            {"filename": "yarn.lock", "status": "modified", "patch": "@@ -1 +1 @@"},
            {"filename": "logo.ico", "status": "modified", "patch": None},
        ],
    }
    gh = FakeGitHub(latest_commit=custom_commit)

    commit_ctx, early_result = await run_collector(sample_request, gh, dummy_verification)
    assert early_result is not None
    assert early_result.status == "no_editable_changes"
    assert "no editable source files found" in early_result.reason.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,is_rl,expected_substring",
    [
        (401, False, "401 Unauthorized"),
        (403, False, "403 Forbidden"),
        (403, True, "rate limit exceeded"),
        (404, False, "404 Not Found"),
    ],
)
async def test_collector_github_error_handling(
    sample_request: FixRequest,
    dummy_verification: VerificationResult,
    status_code: int,
    is_rl: bool,
    expected_substring: str,
):
    """Ensure HTTP errors from GitHub are cleanly handled with github_error status."""
    gh = FakeGitHub(
        error_to_raise=GitHubClientError(status_code, "API failure", is_rate_limit=is_rl)
    )

    commit_ctx, early_result = await run_collector(sample_request, gh, dummy_verification)
    assert commit_ctx is None
    assert early_result is not None
    assert early_result.status == "github_error"
    assert expected_substring in early_result.reason
