"""Dependency injection container for Kawach GitHub Fix Pipeline."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from pydantic import SecretStr

from kawach_fix.clients.github import GitHubClient, HttpxGitHubClient
from kawach_fix.clients.llm import LLMClient, get_default_llm_client
from kawach_fix.clients.runner import PlaywrightScriptRunner, ScriptRunner
from kawach_fix.config import DEFAULT_RUNS_DIR


@dataclass
class Deps:
    """External dependencies container for runner, GitHub API, and LLM services."""

    runner: ScriptRunner = field(default_factory=PlaywrightScriptRunner)
    github: Optional[GitHubClient] = None
    llm: Optional[LLMClient] = None
    runs_dir: Path = field(default_factory=lambda: DEFAULT_RUNS_DIR)

    def resolve_github_client(self, pat: SecretStr) -> GitHubClient:
        """Return the injected GitHubClient or instantiate a new HttpxGitHubClient."""
        if self.github is not None:
            return self.github
        return HttpxGitHubClient(token=pat)

    def resolve_llm_client(self) -> LLMClient:
        """Return the injected LLMClient or instantiate from environment variables."""
        if self.llm is not None:
            return self.llm
        return get_default_llm_client()
