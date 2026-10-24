"""GitHub Collector Agent: extracts and filters changed files from origin/main."""

from pathlib import Path
from typing import List, Optional, Tuple

from kawach_fix.clients.github import GitHubClient, GitHubClientError
from kawach_fix.config import BINARY_EXTENSIONS, GENERATED_PATH_SNIPPETS, LOCKFILES
from kawach_fix.schemas import (
    CommitContext,
    CommitSummary,
    FilePatch,
    FixOptions,
    FixRequest,
    FixResult,
    SkippedFile,
    VerificationResult,
)


def is_binary_or_generated(path_str: str) -> Optional[str]:
    """Check if a file path belongs to binary, lockfile, or generated artifacts."""
    filename = Path(path_str).name
    lower_path = path_str.lower().replace("\\", "/")

    if filename in LOCKFILES:
        return f"Dependency lockfile '{filename}' is managed by package managers."

    suffix = Path(path_str).suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return f"Binary file extension '{suffix}' cannot be edited via text search-and-replace."

    for snip in GENERATED_PATH_SNIPPETS:
        if snip in lower_path:
            return f"Generated, minified, or build artifact matching '{snip}'."

    return None


async def run_collector(
    request: FixRequest,
    github: GitHubClient,
    verification: VerificationResult,
) -> Tuple[Optional[CommitContext], Optional[FixResult]]:
    """Fetch latest commit on origin/main and extract editable files."""
    repo = request.repo
    opts: FixOptions = request.options

    try:
        commit_data = await github.get_latest_main_commit(repo)
    except GitHubClientError as e:
        status_code = e.status_code
        if status_code == 401:
            msg = "GitHub authentication failed: invalid or expired GitHub PAT (401 Unauthorized)."
        elif status_code == 403:
            if e.is_rate_limit:
                msg = "GitHub API rate limit exceeded (403 Forbidden)."
            else:
                msg = "GitHub permission denied: PAT lacks required repository read permissions (403 Forbidden)."
        elif status_code == 404:
            msg = f"Target repository '{repo}' or branch 'main' was not found (404 Not Found)."
        elif e.is_rate_limit:
            msg = "GitHub API rate limit exceeded."
        else:
            msg = f"GitHub API error ({status_code}): {e.message}"

        return None, FixResult(
            status="github_error",
            reason=msg,
            verification=verification,
        )
    except Exception as e:
        return None, FixResult(
            status="github_error",
            reason=f"Failed to query GitHub API: {str(e)}",
            verification=verification,
        )

    pinned_sha = commit_data.get("sha", "")
    message = commit_data.get("message", "")
    author = commit_data.get("author", "Unknown")
    raw_files = commit_data.get("files", [])

    files: List[FilePatch] = []
    skipped: List[SkippedFile] = []

    for file_obj in raw_files:
        fpath = file_obj.get("filename", "")
        fstatus = file_obj.get("status", "")
        patch = file_obj.get("patch")

        # 1. Skip removed files
        if fstatus == "removed":
            skipped.append(SkippedFile(path=fpath, reason="File was deleted in this commit."))
            continue

        # 2. Skip files with no patch (binary changes or pure mode changes)
        if patch is None:
            skipped.append(SkippedFile(path=fpath, reason="File has no text patch diff."))
            continue

        # 3. Check for lockfile, minified, or generated paths
        skip_reason = is_binary_or_generated(fpath)
        if skip_reason:
            skipped.append(SkippedFile(path=fpath, reason=skip_reason))
            continue

        # 4. Enforce max_files limit
        if len(files) >= opts.max_files:
            skipped.append(
                SkippedFile(
                    path=fpath,
                    reason=f"Exceeded max_files limit ({opts.max_files}); skipped remaining files.",
                )
            )
            continue

        # 5. Fetch full content at pinned sha
        try:
            content, blob_sha = await github.get_file_content(repo, fpath, pinned_sha)
        except Exception as e:
            skipped.append(
                SkippedFile(path=fpath, reason=f"Failed to fetch content at commit sha: {str(e)}")
            )
            continue

        # 6. Enforce max_file_bytes limit
        if len(content.encode("utf-8")) > opts.max_file_bytes:
            skipped.append(
                SkippedFile(
                    path=fpath,
                    reason=(
                        f"File size ({len(content.encode('utf-8'))} bytes) exceeds "
                        f"max_file_bytes limit ({opts.max_file_bytes} bytes)."
                    ),
                )
            )
            continue

        # 7. Truncate patch if exceeding max_patch_chars
        truncated = False
        patch_str = patch
        if len(patch) > opts.max_patch_chars:
            patch_str = patch[: opts.max_patch_chars]
            truncated = True

        files.append(
            FilePatch(
                path=fpath,
                status=fstatus,
                patch=patch_str,
                content_at_sha=content,
                blob_sha=blob_sha,
                truncated=truncated,
            )
        )

    commit_context = CommitContext(
        sha=pinned_sha,
        message=message,
        author=author,
        files=files,
        skipped=skipped,
    )

    commit_summary = CommitSummary(
        sha=pinned_sha,
        message=message,
        files=[f.path for f in files],
    )

    if not files:
        return commit_context, FixResult(
            status="no_editable_changes",
            reason=(
                f"No editable source files found in commit {pinned_sha[:7]} "
                f"({len(skipped)} files were skipped due to filtering rules or limits)."
            ),
            verification=verification,
            commit=commit_summary,
        )

    return commit_context, None
