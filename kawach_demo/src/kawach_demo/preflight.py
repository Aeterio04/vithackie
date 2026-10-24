"""Preflight verification checks for Kawach Demo Harness."""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from kawach_demo.config import DemoConfig, load_config
from kawach_demo.github_admin import GitHubAdmin
from kawach_demo.gitops import GitOpsManager, GitOpsError
from kawach_demo.llm_chain import ResilientLLMChain
from kawach_demo.redact import redact_text

console = Console()


async def check_target_url(target_url: str) -> Tuple[bool, str]:
    """Check if the local dev server is responding at TARGET_URL."""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.get(target_url)
            if res.status_code == 200:
                return True, f"Online and responding at {target_url} (HTTP 200)"
            return False, f"Server returned status {res.status_code} at {target_url}"
    except Exception as e:
        return False, f"Connection refused or timed out at {target_url}: {e}"


async def check_github_pat(admin: GitHubAdmin, repo: str) -> Tuple[bool, str]:
    """Verify PAT validity and Contents RW + Pull Requests RW permissions."""
    try:
        res = await admin.check_repo_and_scopes()
        if not res.get("ok"):
            err = res.get("error", "Unknown permission failure")
            return False, f"GitHub permission error: {err}"
        return True, f"Verified RW access (Contents & PRs) for repo: {repo}"
    except Exception as e:
        return False, f"GitHub check failed: {e}"


async def check_llm_connectivity(llm: ResilientLLMChain) -> Tuple[bool, str]:
    """Verify live LLM connectivity with a tiny JSON request."""
    try:
        sys_prompt = "You are a healthcheck agent. Respond with valid JSON {\"status\": \"ok\"}."
        user_prompt = "ping"
        res = await llm.generate(sys_prompt, user_prompt, temperature=0.0)
        provider = llm.last_provider or "LLM"
        latency = llm.last_latency_sec
        return True, f"Connected to {provider} ({llm.last_model}) - response in {latency:.2f}s"
    except Exception as e:
        return False, f"LLM call failed: {e}"


def check_playwright(clone_path: Path) -> Tuple[bool, str]:
    """Check if npx playwright is available in the target app environment."""
    npx_bin = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_bin:
        return False, "npx executable not found in PATH"

    cmd = [npx_bin, "playwright", "--version"]
    try:
        res = subprocess.run(
            cmd,
            cwd=str(clone_path) if clone_path.exists() else None,
            capture_output=True,
            text=True,
            shell=(os.name == "nt"),
            check=False,
            timeout=10,
        )
        if res.returncode == 0:
            version_str = (res.stdout or "").strip()
            return True, f"Playwright available ({version_str})"
        return False, f"npx playwright returned exit {res.returncode}: {res.stderr.strip()}"
    except Exception as e:
        return False, f"Playwright execution failed: {e}"


def check_local_clone(gitops: GitOpsManager, expected_tag: str = "demo-good") -> Tuple[bool, str]:
    """Verify that APP_CLONE_PATH is a clean clone on main at demo-good."""
    clone_path = gitops.clone_path
    if not clone_path.exists() or not (clone_path / ".git").is_dir():
        return False, f"Directory is not a valid git repository: {clone_path}"

    try:
        branch = gitops.get_current_branch()
        if branch != "main":
            return False, f"Clone is on branch '{branch}', expected 'main'"

        if not gitops.verify_clean():
            return False, "Clone working tree has uncommitted or untracked changes"

        if not gitops.check_tag_exists(expected_tag):
            return False, f"Expected tag '{expected_tag}' does not exist in clone"

        tag_sha = gitops.run_git("rev-parse", expected_tag)
        current_sha = gitops.get_current_sha()
        if tag_sha != current_sha:
            return False, f"HEAD ({current_sha[:7]}) is not at tag {expected_tag} ({tag_sha[:7]})"

        return True, f"Clean on branch 'main' at tag '{expected_tag}' ({current_sha[:7]})"
    except GitOpsError as e:
        return False, f"Git inspection failed: {e}"


async def check_stale_branches_and_prs(admin: GitHubAdmin) -> Tuple[bool, str]:
    """Verify there are no leftover kawach/fix-* branches or open PRs."""
    try:
        prs = await admin.list_open_fix_prs()
        branches = await admin.list_fix_branches()

        if prs or branches:
            msg = []
            if prs:
                msg.append(f"{len(prs)} open PR(s)")
            if branches:
                msg.append(f"{len(branches)} stale branch(es)")
            return False, f"Found {', '.join(msg)}. Run `reset` before demo."
        return True, "No stale kawach/fix-* branches or open PRs"
    except Exception as e:
        return False, f"Failed to check GitHub branches/PRs: {e}"


async def run_preflight(config: DemoConfig) -> bool:
    """Execute all preflight checks and print a formatted Rich checklist table."""
    admin = GitHubAdmin(config.github_pat, config.demo_repo)
    gitops = GitOpsManager(config.app_clone_path, config.github_pat)
    llm = ResilientLLMChain(config.groq_api_key, config.gemini_api_key)

    secrets = [s.get_secret_value() for s in config.secrets_list]

    table = Table(title="[bold cyan]Kawach Demo Harness — Preflight Inspection[/bold cyan]", show_lines=True)
    table.add_column("Item", style="bold white", width=24)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Details", style="dim")

    all_passed = True

    checks = [
        ("Target App Online", lambda: check_target_url(config.target_url)),
        ("GitHub PAT & Scopes", lambda: check_github_pat(admin, config.demo_repo)),
        ("Live LLM Provider", lambda: check_llm_connectivity(llm)),
        ("Playwright Test Runner", lambda: asyncio.to_thread(check_playwright, config.app_clone_path)),
        ("Local Git Clone", lambda: asyncio.to_thread(check_local_clone, gitops, "demo-good")),
        ("Stale Branches & PRs", lambda: check_stale_branches_and_prs(admin)),
    ]

    for label, check_fn in checks:
        passed, details = await check_fn()
        redacted_details = redact_text(details, secrets)
        if passed:
            status_cell = "[bold green]PASS[/bold green]"
        else:
            status_cell = "[bold red]FAIL[/bold red]"
            all_passed = False
        table.add_row(label, status_cell, redacted_details)

    console.print()
    console.print(table)
    console.print()

    if all_passed:
        console.print(Panel(
            "[bold green][PASS] All preflight checks passed successfully![/bold green]\n"
            "The demo harness is ready to run.",
            border_style="green",
        ))
    else:
        console.print(Panel(
            "[bold red][FAIL] Preflight checks failed.[/bold red]\n"
            "Please resolve the failing items above before starting the live demo.",
            border_style="red",
        ))

    return all_passed
