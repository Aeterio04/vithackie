"""Rehearsal automation evaluating LLM fix accuracy and timing with extensive live logging."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from kawach_demo.config import DemoConfig
from kawach_demo.gitops import GitOpsManager
from kawach_demo.instrumented import make_instrumented_deps
from kawach_demo.llm_chain import ResilientLLMChain
from kawach_demo.narrator import Narrator
from kawach_demo.runner import RobustPlaywrightRunner
from kawach_demo.scenes import load_catalog
from kawach_fix.clients.github import HttpxGitHubClient
from kawach_fix.deps import Deps
from kawach_fix.graph import arun_fix_pipeline
from kawach_fix.schemas import ErrorReport, FixOptions, FixRequest, FixResult


@dataclass
class BugRehearsalResult:
    """Metrics gathered across multiple trial executions for a bug."""

    bug_id: str
    trials: int
    proposals_reached: int = 0
    edits_valid: int = 0
    test_passed_with_fix: int = 0
    total_duration_sec: float = 0.0
    providers_used: List[str] = None

    def __post_init__(self):
        if self.providers_used is None:
            self.providers_used = []


async def run_single_trial(
    config: DemoConfig,
    gitops: GitOpsManager,
    bug_id: str,
    bugs_dir: Path,
    llm_chain: ResilientLLMChain,
    narrator: Narrator,
) -> Dict[str, Any]:
    """Execute 1 full rehearsal iteration with extensive real-time logging."""
    catalog = load_catalog(bugs_dir / "catalog.json")
    bug_info = catalog.get(bug_id, catalog["bug_1"])
    patch_file = bugs_dir / f"{bug_id}.patch"

    narrator.console.print(f"\n[bold cyan]┌── Starting Trial for {bug_id}: {bug_info['title']}[/bold cyan]")

    # 1. Reset to clean tag
    narrator.console.print("  [dim]• Resetting local clone & origin/main to 'demo-good'...[/dim]")
    gitops.reset_to_tag("demo-good")
    await asyncio.sleep(1.0)

    # 2. Plant bug
    narrator.console.print(f"  [dim]• Planting bug commit: '{bug_info['commit_message']}'...[/dim]")
    new_sha = gitops.plant_bug(patch_file, bug_info["commit_message"])
    narrator.console.print(f"    [green]✓ Pushed bug commit {new_sha[:8]} to origin/main[/green]")
    await asyncio.sleep(1.5)

    # 3. Run fix pipeline in dry_run mode with extensive instrumentation
    cart_spec = "tests/cart.spec.ts"
    req = FixRequest(
        repo=config.demo_repo,
        github_pat=config.github_pat,
        base_branch="main",
        error=ErrorReport(
            test_name="tests/cart.spec.ts",
            failing_step="expect(locator).toHaveText('$61.56')",
            message="AssertionError: Expected totals did not match actual totals.",
        ),
        playwright_script=cart_spec,
        target_url=config.target_url,
        playwright_project_dir=str(config.app_clone_path),
        options=FixOptions(verify_runs=3, min_failures=2, dry_run=True, run_timeout_sec=30),
    )

    runner = RobustPlaywrightRunner()
    raw_deps = Deps(
        runner=runner,
        github=HttpxGitHubClient(token=config.github_pat),
        llm=llm_chain,
        runs_dir=config.runs_dir,
    )
    inst_deps = make_instrumented_deps(raw_deps, narrator, total_runs=3)

    t0 = time.perf_counter()
    narrator.console.print("  [dim]• Running fix pipeline (verification -> git inspect -> LLM repair)...[/dim]")
    result: FixResult = await arun_fix_pipeline(req, deps=inst_deps)
    dt = time.perf_counter() - t0

    has_proposal = result.proposal is not None
    is_valid = result.status == "dry_run_ready"
    test_passed = False
    provider = llm_chain.last_provider or "Unknown"

    if result.proposal:
        narrator.console.print(f"\n  [bold green]✓ LLM Repair Proposed via {provider} ({llm_chain.last_model}) in {dt:.1f}s:[/bold green]")
        narrator.console.print(f"    [dim]Root cause:[/dim] {result.proposal.root_cause}")
        narrator.console.print(f"    [dim]Confidence:[/dim] {result.proposal.confidence * 100:.0f}%")
        for edit in result.proposal.edits:
            narrator.console.print(f"    [yellow]File:[/yellow] {edit.path}")
            narrator.console.print(f"    [red]- {edit.old_str.strip()}[/red]")
            narrator.console.print(f"    [green]+ {edit.new_str.strip()}[/green]")
    else:
        narrator.console.print(f"  [red]✗ Pipeline halted without valid proposal: status={result.status}, reason={result.reason}[/red]")

    # 4. If valid edits returned, apply to working tree and test
    if is_valid and result.proposal and result.proposal.edits:
        try:
            narrator.console.print("\n  [dim]• Applying proposal to local clone working tree...[/dim]")
            gitops.apply_edits_locally(result.proposal.edits)
            narrator.console.print("    [green]✓ Working tree updated successfully.[/green]")

            narrator.console.print("  [dim]• Waiting for hot reload (2.0s)...[/dim]")
            await asyncio.sleep(2.0)

            narrator.console.print("  [dim]• Executing cart.spec.ts against running target app...[/dim]")
            test_run = await runner.run_test(
                script_path_or_code=cart_spec,
                target_url=config.target_url,
                project_dir=str(config.app_clone_path),
                timeout_sec=30,
                run_index=1,
            )
            test_passed = test_run.passed
            if test_passed:
                narrator.console.print("    [bold green]✓ POST-FIX TEST PASSED! The repair is confirmed effective.[/bold green]")
            else:
                err_preview = (test_run.error_text or "")[:180].replace("\n", " ")
                narrator.console.print(f"    [bold red]✗ POST-FIX TEST FAILED:[/bold red] {err_preview}")
        except Exception as e:
            narrator.console.print(f"    [bold red]✗ Error applying edits or executing test:[/bold red] {e}")
            test_passed = False
        finally:
            narrator.console.print("  [dim]• Reverting working tree back to clean state...[/dim]")
            gitops.revert_working_tree()

    narrator.console.print(f"[bold cyan]└── End Trial: Passed={test_passed} in {dt:.1f}s[/bold cyan]\n")

    return {
        "reached_proposal": has_proposal,
        "edits_valid": is_valid,
        "test_passed": test_passed,
        "duration_sec": dt,
        "provider": provider,
    }


async def run_rehearsal(
    config: DemoConfig,
    gitops: GitOpsManager,
    bugs: List[str],
    repetitions: int,
    bugs_dir: Path,
    narrator: Narrator,
):
    """Run full rehearsal matrix, print scoreboard, and recommend live demo choice."""
    narrator.console.print("\n[bold cyan]🎯 Commencing Multi-Bug Autonomous Rehearsal Matrix[/bold cyan]")
    narrator.console.print(f"[dim]Bugs: {', '.join(bugs)}  |  Repetitions: {repetitions}x  |  Mode: dry_run=True[/dim]\n")

    llm_chain = ResilientLLMChain(
        groq_api_key=config.groq_api_key,
        gemini_api_key=config.gemini_api_key,
    )

    results: Dict[str, BugRehearsalResult] = {}

    try:
        for bug_id in bugs:
            rec = BugRehearsalResult(bug_id=bug_id, trials=repetitions)
            narrator.console.print(f"\n[bold yellow]══════ Testing {bug_id} ({repetitions} repetition(s)) ══════[/bold yellow]")

            for trial_idx in range(1, repetitions + 1):
                narrator.console.print(f"\n[dim]─── Trial {trial_idx}/{repetitions} for {bug_id} ───[/dim]")
                trial_res = await run_single_trial(
                    config=config,
                    gitops=gitops,
                    bug_id=bug_id,
                    bugs_dir=bugs_dir,
                    llm_chain=llm_chain,
                    narrator=narrator,
                )
                if trial_res["reached_proposal"]:
                    rec.proposals_reached += 1
                if trial_res["edits_valid"]:
                    rec.edits_valid += 1
                if trial_res["test_passed"]:
                    rec.test_passed_with_fix += 1
                rec.total_duration_sec += trial_res["duration_sec"]
                if trial_res["provider"] not in rec.providers_used:
                    rec.providers_used.append(trial_res["provider"])

            results[bug_id] = rec

    finally:
        # Always reset origin/main back to demo-good
        narrator.console.print("\n[dim]Resetting target repository back to 'demo-good'...[/dim]")
        gitops.reset_to_tag("demo-good")

    # Render Rehearsal Summary Table
    table = Table(title="Autonomous Rehearsal Scoreboard", border_style="cyan", padding=(0, 1))
    table.add_column("Bug ID", style="bold yellow")
    table.add_column("Trials", justify="center")
    table.add_column("Proposal Reached", justify="center")
    table.add_column("Edits Valid", justify="center")
    table.add_column("Fix Passes Test", justify="center", style="bold green")
    table.add_column("Avg Sec", justify="right")
    table.add_column("Provider", style="magenta")

    best_bug: Optional[str] = None
    best_score = -1

    for bug_id, res in results.items():
        avg_s = res.total_duration_sec / res.trials if res.trials else 0
        table.add_row(
            bug_id,
            str(res.trials),
            f"{res.proposals_reached}/{res.trials}",
            f"{res.edits_valid}/{res.trials}",
            f"{res.test_passed_with_fix}/{res.trials}",
            f"{avg_s:.1f}s",
            ", ".join(res.providers_used) if res.providers_used else "None",
        )
        if res.test_passed_with_fix > best_score:
            best_score = res.test_passed_with_fix
            best_bug = bug_id

    narrator.console.print()
    narrator.console.print(table)
    narrator.console.print()
    if best_bug:
        narrator.console.print(
            f"[bold green]⭐ Recommended Bug for Live Presentation:[/bold green] [bold yellow]{best_bug}[/bold yellow] "
            f"(Passed {best_score}/{repetitions} verification trials cleanly)"
        )
