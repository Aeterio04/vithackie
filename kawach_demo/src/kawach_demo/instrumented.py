"""Logging and event-emitting instrumentation wrappers around Deps interfaces."""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import SecretStr

from kawach_demo.narrator import Narrator
from kawach_fix.clients.github import GitHubClient
from kawach_fix.clients.llm import LLMClient
from kawach_fix.clients.runner import ScriptRunner
from kawach_fix.deps import Deps
from kawach_fix.schemas import PullRequestInfo, RunItem


class InstrumentedRunner(ScriptRunner):
    """Wraps ScriptRunner to narrate each Playwright execution attempt."""

    def __init__(self, inner: ScriptRunner, narrator: Narrator, total_runs: int = 3):
        self.inner = inner
        self.narrator = narrator
        self.total_runs = total_runs

    async def run_test(
        self,
        script_path_or_code: str,
        target_url: str,
        project_dir: str,
        timeout_sec: int,
        run_index: int = 1,
    ) -> RunItem:
        item = await self.inner.run_test(
            script_path_or_code=script_path_or_code,
            target_url=target_url,
            project_dir=project_dir,
            timeout_sec=timeout_sec,
            run_index=run_index,
        )
        self.narrator.on_replay_run(
            index=item.index,
            total=self.total_runs,
            passed=item.passed,
            duration_ms=item.duration_ms,
            error_text=item.error_text,
        )
        return item


class InstrumentedGitHub(GitHubClient):
    """Wraps GitHubClient to narrate commit collection and PR creation."""

    def __init__(self, inner: GitHubClient, narrator: Narrator):
        self.inner = inner
        self.narrator = narrator

    async def get_latest_main_commit(self, repo: str) -> Dict[str, Any]:
        self.narrator.step("Fetching latest commit on origin/main...", "running")
        commit_data = await self.inner.get_latest_main_commit(repo)
        sha = commit_data.get("sha", "")
        message = commit_data.get("message", "")
        author = commit_data.get("author", "")
        files = [f.get("filename", "") for f in commit_data.get("files", [])]

        self.narrator.step("Pinned origin/main commit", "success", f"{sha[:7]} ({len(files)} files)")
        self.narrator.on_commit_collected(sha, message, author, files)
        return commit_data

    async def get_file_content(self, repo: str, path: str, ref: str) -> Tuple[str, str]:
        return await self.inner.get_file_content(repo, path, ref)

    async def get_ref(self, repo: str, branch_name: str) -> Optional[str]:
        return await self.inner.get_ref(repo, branch_name)

    async def create_ref(self, repo: str, branch_name: str, sha: str) -> None:
        self.narrator.step(f"Creating repair branch '{branch_name}'...", "running")
        await self.inner.create_ref(repo, branch_name, sha)
        self.narrator.step(f"Created branch '{branch_name}'", "success")

    async def update_file(
        self,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        blob_sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.narrator.step(f"Committing patch to '{path}'...", "running")
        res = await self.inner.update_file(repo, path, content, message, branch, blob_sha)
        self.narrator.step(f"Committed patch to '{path}'", "success")
        return res

    async def find_existing_pr(
        self, repo: str, head_branch: str, base_branch: str = "main"
    ) -> Optional[PullRequestInfo]:
        return await self.inner.find_existing_pr(repo, head_branch, base_branch)

    async def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        draft: bool = False,
    ) -> PullRequestInfo:
        self.narrator.step("Opening Pull Request into main...", "running")
        pr_info = await self.inner.create_pr(repo, title, body, head_branch, base_branch, draft)
        self.narrator.on_pr_raised(pr_info.number, pr_info.url, head_branch, title)
        return pr_info


class InstrumentedLLM(LLMClient):
    """Wraps LLMClient to narrate prompt dispatch and synthesis timing."""

    def __init__(self, inner: LLMClient, narrator: Narrator):
        self.inner = inner
        self.narrator = narrator

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        self.narrator.step("Consulting LLM for exact patch synthesis...", "running")
        t0 = time.perf_counter()
        resp = await self.inner.generate(system_prompt, user_prompt, temperature)
        dt = time.perf_counter() - t0

        provider = getattr(self.inner, "last_provider", "LLM")
        model = getattr(self.inner, "last_model", "")
        detail = f"using {provider} ({model}) in {dt:.1f}s" if model else f"using {provider} in {dt:.1f}s"
        self.narrator.step("Model repair synthesis complete", "success", detail)
        return resp


def make_instrumented_deps(deps: Deps, narrator: Narrator, total_runs: int = 3) -> Deps:
    """Wrap real or mock Deps components with real-time narrator instrumentation."""
    inst_runner = InstrumentedRunner(deps.runner, narrator, total_runs=total_runs)

    inst_github = None
    if deps.github:
        inst_github = InstrumentedGitHub(deps.github, narrator)

    inst_llm = None
    if deps.llm:
        inst_llm = InstrumentedLLM(deps.llm, narrator)

    return Deps(
        runner=inst_runner,
        github=inst_github,
        llm=inst_llm,
        runs_dir=deps.runs_dir,
    )
