"""PR Raiser Agent: applies edits and creates GitHub branch and pull request."""

from typing import Dict, List, Optional, Tuple

from kawach_fix.clients.github import GitHubClient, GitHubClientError
from kawach_fix.config import BRANCH_PREFIX, COMMIT_MSG_PREFIX, PR_FOOTER
from kawach_fix.schemas import (
    CommitContext,
    CommitSummary,
    FixProposal,
    FixRequest,
    FixResult,
    PullRequestInfo,
    VerificationResult,
)


def build_pr_body(
    request: FixRequest,
    verification: VerificationResult,
    commit_context: CommitContext,
    proposal: FixProposal,
) -> str:
    """Build deterministic pull request description using structured fields."""
    modified_files = sorted(list({e.path for e in proposal.edits}))
    files_bullets = "\n".join(f"- `{p}`" for p in modified_files)

    body = f"""## Autonomous Defect Repair (Kawach Fix Pipeline)

### Test Verification
- **Failing Test:** `{request.error.test_name}`
- **Failing Step:** `{request.error.failing_step or 'N/A'}`
- **Verification Runs:** `{verification.failures}/{request.options.verify_runs} failures confirmed`
- **Observed Error:** `{verification.observed_error or request.error.message}`

### Commit Context
- **Base Commit:** `{commit_context.sha[:7]}` (`{commit_context.sha}`)
- **Commit Message:** `{commit_context.message}`
- **Author:** `{commit_context.author}`

### Root Cause Analysis
{proposal.root_cause}

### Fix Summary
{proposal.explanation}
*(Confidence Score: {proposal.confidence * 100:.0f}%)*

### Modified Files
{files_bullets}
{PR_FOOTER}"""
    return body


async def run_pr_raiser(
    request: FixRequest,
    github: GitHubClient,
    verification: VerificationResult,
    commit_context: CommitContext,
    proposal: FixProposal,
) -> Tuple[Optional[PullRequestInfo], FixResult]:
    """Apply edits in memory and open a pull request into origin/main."""
    repo = request.repo
    pinned_sha = commit_context.sha
    branch_name = f"{BRANCH_PREFIX}{pinned_sha[:7]}"

    commit_summary = CommitSummary(
        sha=pinned_sha,
        message=commit_context.message,
        files=[f.path for f in commit_context.files],
    )

    # 1. Apply edits in-memory to calculate final file contents
    files_by_path = {f.path: f for f in commit_context.files}
    final_contents: Dict[str, str] = {
        f.path: f.content_at_sha or "" for f in commit_context.files
    }
    for edit in proposal.edits:
        curr = final_contents[edit.path]
        final_contents[edit.path] = curr.replace(edit.old_str, edit.new_str, 1)

    modified_paths = sorted(list({e.path for e in proposal.edits}))

    # 2. Check for existing open PR (idempotence)
    try:
        existing_pr = await github.find_existing_pr(repo, branch_name, base_branch="main")
        if existing_pr:
            return existing_pr, FixResult(
                status="pr_exists",
                reason=f"An open pull request already exists for branch '{branch_name}': {existing_pr.url}",
                verification=verification,
                commit=commit_summary,
                proposal=proposal,
                pull_request=existing_pr,
            )
    except GitHubClientError as e:
        return None, FixResult(
            status="github_error",
            reason=f"Failed to check existing pull requests on GitHub: {e.message}",
            verification=verification,
            commit=commit_summary,
            proposal=proposal,
        )

    # 3. Handle dry run mode (zero write calls)
    pr_title = proposal.pr_title or f"{COMMIT_MSG_PREFIX} repair {request.error.test_name}"
    if not pr_title.startswith(COMMIT_MSG_PREFIX):
        pr_title = f"{COMMIT_MSG_PREFIX} {pr_title}"

    pr_body = build_pr_body(request, verification, commit_context, proposal)

    if request.options.dry_run:
        would_be_pr = PullRequestInfo(
            number=None,
            url=None,
            branch=branch_name,
            created=False,
        )
        return would_be_pr, FixResult(
            status="dry_run_ready",
            reason=(
                f"Dry run complete: verified defect, generated valid patch for "
                f"{len(modified_paths)} files on branch '{branch_name}'. Zero GitHub writes performed."
            ),
            verification=verification,
            commit=commit_summary,
            proposal=proposal,
            pull_request=would_be_pr,
        )

    # 4. Perform GitHub write operations
    try:
        # Check if branch ref already exists, otherwise create it from pinned sha
        existing_branch_sha = await github.get_ref(repo, branch_name)
        if not existing_branch_sha:
            await github.create_ref(repo, branch_name, pinned_sha)

        # Write each modified file via Contents API
        for path in modified_paths:
            blob_sha = files_by_path[path].blob_sha
            new_text = final_contents[path]
            commit_msg = f"{COMMIT_MSG_PREFIX} update {path}"
            await github.update_file(
                repo=repo,
                path=path,
                content=new_text,
                message=commit_msg,
                branch=branch_name,
                blob_sha=blob_sha,
            )

        # Open Pull Request
        pr_info = await github.create_pr(
            repo=repo,
            title=pr_title,
            body=pr_body,
            head_branch=branch_name,
            base_branch="main",
            draft=request.options.draft_pr,
        )

        return pr_info, FixResult(
            status="pr_opened",
            reason=f"Successfully opened pull request #{pr_info.number} into main: {pr_info.url}",
            verification=verification,
            commit=commit_summary,
            proposal=proposal,
            pull_request=pr_info,
        )

    except GitHubClientError as e:
        return None, FixResult(
            status="github_error",
            reason=f"GitHub write operation failed ({e.status_code}): {e.message}",
            verification=verification,
            commit=commit_summary,
            proposal=proposal,
        )
    except Exception as e:
        return None, FixResult(
            status="github_error",
            reason=f"Unexpected error creating pull request: {str(e)}",
            verification=verification,
            commit=commit_summary,
            proposal=proposal,
        )
