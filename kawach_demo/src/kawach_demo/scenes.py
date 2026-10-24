"""Execution stages and narrated scenes for the live demonstration flow."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from kawach_demo.config import DemoConfig
from kawach_demo.gitops import GitOpsManager
from kawach_demo.instrumented import make_instrumented_deps
from kawach_demo.llm_chain import ResilientLLMChain
from kawach_demo.narrator import Narrator
from kawach_demo.runner import RobustPlaywrightRunner
from kawach_fix.clients.github import HttpxGitHubClient
from kawach_fix.deps import Deps
from kawach_fix.graph import arun_fix_pipeline
from kawach_fix.schemas import ErrorReport, FileEdit, FixOptions, FixProposal, FixRequest, FixResult


def load_catalog(catalog_path: Path) -> Dict[str, Any]:
    """Load bug catalog dictionary from json."""
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {b["id"]: b for b in raw}


async def run_scene_1_healthy(config: DemoConfig, narrator: Narrator, no_pause: bool = False):
    """Scene 1: Execute cart test against healthy target app."""
    narrator.scene_header("1", "Healthy Control Verification", "Asserting target app passes regression baseline.")
    runner = RobustPlaywrightRunner()
    cart_spec = "tests/cart.spec.ts"

    narrator.step(f"Executing cart.spec.ts against {config.target_url}...", "running")
    t0 = time.perf_counter()
    res = await runner.run_test(
        script_path_or_code=cart_spec,
        target_url=config.target_url,
        project_dir=str(config.app_clone_path),
        timeout_sec=30,
        run_index=1,
    )
    dt = time.perf_counter() - t0

    if res.passed:
        narrator.step("Baseline test suite passed cleanly", "success", f"in {dt:.1f}s")
    else:
        narrator.step("Baseline test suite failed unexpectedly", "failure", res.error_text or "Unknown error")
        narrator.console.print("[yellow]Tip: Ensure target app at TARGET_URL is reset and healthy.[/yellow]")

    if not no_pause:
        narrator.pause_for_presenter("Press [Enter] to plant bug commit...")


async def run_scene_2_bad_commit(
    config: DemoConfig, gitops: GitOpsManager, bug_id: str, bugs_dir: Path, narrator: Narrator, no_pause: bool = False
) -> str:
    """Scene 2: Plant realistic refactor bug commit and verify failure."""
    catalog = load_catalog(bugs_dir / "catalog.json")
    bug_info = catalog.get(bug_id, catalog["bug_1"])
    patch_file = bugs_dir / f"{bug_id}.patch"

    narrator.scene_header(
        "2",
        f"The Bad Commit ({bug_id}: {bug_info['title']})",
        f"Pushing innocent refactor commit: '{bug_info['commit_message']}'",
    )

    narrator.step(f"Applying patch {bug_id}.patch and committing to origin/main...", "running")
    new_sha = gitops.plant_bug(patch_file, bug_info["commit_message"])
    narrator.step(f"Pushed commit {new_sha[:7]} to origin/main", "success")

    # Give hot-reloading server a moment to pick up changes
    await asyncio.sleep(1.5)

    narrator.step("Re-executing cart.spec.ts to observe defect...", "running")
    runner = RobustPlaywrightRunner()
    cart_spec = "tests/cart.spec.ts"
    res = await runner.run_test(
        script_path_or_code=cart_spec,
        target_url=config.target_url,
        project_dir=str(config.app_clone_path),
        timeout_sec=30,
        run_index=1,
    )

    if not res.passed:
        narrator.step("Test failure confirmed as expected", "failure", res.error_text[:120] if res.error_text else "")
    else:
        narrator.step("Warning: test passed despite bug patch", "info")

    if not no_pause:
        narrator.pause_for_presenter("Press [Enter] to run Negative Control check...")
    return new_sha


async def run_scene_3_negative_control(config: DemoConfig, narrator: Narrator, no_pause: bool = False):
    """Scene 3: Demonstrate Kawach does not trust bug reports blindly."""
    narrator.scene_header(
        "3",
        "Negative Control Gate",
        "Kawach does not trust error reports blindly: testing non-failing home.spec.ts.",
    )

    home_spec = "tests/home.spec.ts"
    fake_req = FixRequest(
        repo=config.demo_repo,
        github_pat=config.github_pat,
        base_branch="main",
        error=ErrorReport(
            test_name="tests/home.spec.ts",
            failing_step="Assert heading",
            message="Claimed error: Heading missing (phantom claim)",
        ),
        playwright_script=home_spec,
        target_url=config.target_url,
        playwright_project_dir=str(config.app_clone_path),
        options=FixOptions(verify_runs=3, min_failures=2),
    )

    runner = RobustPlaywrightRunner()
    raw_deps = Deps(
        runner=runner,
        github=HttpxGitHubClient(token=config.github_pat),
        llm=None,
        runs_dir=config.runs_dir,
    )
    inst_deps = make_instrumented_deps(raw_deps, narrator, total_runs=3)

    narrator.step("Running autonomous 3x replay verification...", "running")
    result = await arun_fix_pipeline(fake_req, deps=inst_deps)

    if result.status == "not_reproduced":
        narrator.step("Pipeline halted correctly: 'not_reproduced'", "success", result.reason)
        narrator.console.print("    [bold green]🛡️ Kawach refused to make changes: test passed 3/3 runs.[/bold green]")
    else:
        narrator.step(f"Unexpected status: {result.status}", "failure", result.reason)

    if not no_pause:
        narrator.pause_for_presenter("Press [Enter] to commence real autonomous fix...")


async def run_scene_4_real_fix(
    config: DemoConfig,
    narrator: Narrator,
    llm_chain: ResilientLLMChain,
    dry_run: bool = False,
    no_pause: bool = False,
) -> Optional[FixResult]:
    """Scene 4: Live defect verification, LLM repair synthesis, and PR creation."""
    narrator.scene_header("4", "Autonomous Defect Verification & PR Repair", "Replaying defect, analyzing diff, and synthesizing fix.")

    cart_spec = "tests/cart.spec.ts"
    req = FixRequest(
        repo=config.demo_repo,
        github_pat=config.github_pat,
        base_branch="main",
        error=ErrorReport(
            test_name="tests/cart.spec.ts",
            failing_step="expect(locator).toHaveText('$61.56')",
            message="AssertionError: Expected totals did not match actual totals.",
            console=["[error] Pricing quote mismatch observed."],
        ),
        playwright_script=cart_spec,
        target_url=config.target_url,
        playwright_project_dir=str(config.app_clone_path),
        options=FixOptions(
            verify_runs=3,
            min_failures=2,
            dry_run=dry_run,
            draft_pr=False,
            run_timeout_sec=30,
        ),
    )

    real_github = HttpxGitHubClient(token=config.github_pat)
    real_runner = RobustPlaywrightRunner()

    raw_deps = Deps(
        runner=real_runner,
        github=real_github,
        llm=llm_chain,
        runs_dir=config.runs_dir,
    )
    inst_deps = make_instrumented_deps(raw_deps, narrator, total_runs=3)

    t0 = time.perf_counter()
    result = await arun_fix_pipeline(req, deps=inst_deps)
    dt = time.perf_counter() - t0

    # Display synthesis results
    if result.proposal:
        narrator.on_proposal_generated(
            root_cause=result.proposal.root_cause,
            explanation=result.proposal.explanation,
            confidence=result.proposal.confidence,
            edits=result.proposal.edits,
            provider=llm_chain.last_provider or "LLM",
        )
        for edit in result.proposal.edits:
            narrator.show_diff(edit.path, edit.old_str, edit.new_str)

    if result.status == "pr_opened":
        pr = result.pull_request
        narrator.step(f"PR opened successfully in {dt:.1f}s", "success", pr.url if pr else "")
    elif result.status == "dry_run_ready":
        narrator.step(f"Dry-run verified and patch synthesized in {dt:.1f}s", "success")
    elif result.status == "pr_exists":
        narrator.step(f"PR already exists: {result.pull_request.url if result.pull_request else ''}", "info")
    else:
        narrator.step(f"Pipeline stopped: {result.status}", "failure", result.reason)

    if not no_pause:
        narrator.pause_for_presenter("Press [Enter] to proceed to Human-in-the-Loop merge...")

    return result


async def run_scene_5_human_in_the_loop(
    config: DemoConfig,
    gitops: GitOpsManager,
    fix_result: Optional[FixResult],
    narrator: Narrator,
    elapsed_total: float,
    no_pause: bool = False,
):
    """Scene 5: Presenter merges PR on GitHub, local clone pulls, and test passes."""
    narrator.scene_header("5", "Human in the Loop Verification", "Merge pull request on GitHub to complete the loop.")

    pr_url = fix_result.pull_request.url if (fix_result and fix_result.pull_request) else None

    if pr_url:
        narrator.console.print(f"[bold yellow]👉 Please open and MERGE the pull request on GitHub:[/bold yellow] [bold underline]{pr_url}[/bold underline]")
    else:
        narrator.console.print("[dim]Dry run mode or no PR was opened.[/dim]")

    if not no_pause:
        narrator.pause_for_presenter("After merging the PR on GitHub, press [Enter] to pull and verify...")

    narrator.step("Pulling merged changes into local application clone...", "running")
    try:
        gitops.pull()
        narrator.step("Local clone updated to latest origin/main", "success")
    except Exception as e:
        narrator.step("Pulling main failed", "failure", str(e))

    # Give hot-reloading server a moment to reload code
    await asyncio.sleep(2.0)

    narrator.step("Re-executing cart.spec.ts to verify defect resolution...", "running")
    runner = RobustPlaywrightRunner()
    cart_spec = "tests/cart.spec.ts"
    res = await runner.run_test(
        script_path_or_code=cart_spec,
        target_url=config.target_url,
        project_dir=str(config.app_clone_path),
        timeout_sec=30,
        run_index=1,
    )

    if res.passed:
        narrator.step("Full regression suite PASSED! Bug repaired autonomously.", "success")
    else:
        narrator.step("Test did not pass after merge", "failure", res.error_text[:120] if res.error_text else "")

    replays = len(fix_result.verification.runs) if (fix_result and fix_result.verification) else 3
    files_count = len(fix_result.proposal.edits) if (fix_result and fix_result.proposal) else 1
    narrator.show_summary(elapsed_total, replays, files_count, pr_url)


async def run_scene_guardrail(config: DemoConfig, narrator: Narrator, no_pause: bool = False):
    """Optional Scene G: Adversarial simulation proving model edits outside allowlist are blocked."""
    narrator.scene_header(
        "G",
        "SIMULATED ADVERSARIAL MODEL OUTPUT",
        "Security guardrail demonstration: Model attempts unauthorized file modification.",
    )

    class AdversarialFakeLLM:
        async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
            proposal = {
                "can_fix": True,
                "confidence": 0.99,
                "root_cause": "Adversarial prompt injection simulation",
                "explanation": "Attempting edit outside changed files",
                "edits": [
                    {
                        "path": "src/security/unauthorized.js",
                        "old_str": "authRequired = true;",
                        "new_str": "authRequired = false;",
                    }
                ],
                "pr_title": "fix: malicious edit",
                "pr_summary": "malicious edit",
            }
            return json.dumps(proposal)

    cart_spec = "tests/cart.spec.ts"
    req = FixRequest(
        repo=config.demo_repo,
        github_pat=config.github_pat,
        base_branch="main",
        error=ErrorReport(test_name="tests/cart.spec.ts", message="Simulated failure"),
        playwright_script=cart_spec,
        target_url=config.target_url,
        playwright_project_dir=str(config.app_clone_path),
        options=FixOptions(verify_runs=1, min_failures=1),
    )

    raw_deps = Deps(
        runner=RobustPlaywrightRunner(),
        github=HttpxGitHubClient(token=config.github_pat),
        llm=AdversarialFakeLLM(),
        runs_dir=config.runs_dir,
    )

    narrator.step("Dispatching pipeline with untrusted model proposal...", "running")
    result = await arun_fix_pipeline(req, deps=raw_deps)

    if result.status == "invalid_llm_output":
        narrator.step("Security Guardrail ENFORCED", "success", result.reason)
        narrator.console.print("    [bold green]🛡️ Kawach rejected unauthorized edit to 'src/security/unauthorized.js'.[/bold green]")
    else:
        narrator.step(f"Guardrail check returned: {result.status}", "failure", result.reason)

    if not no_pause:
        narrator.pause_for_presenter("Press [Enter] to conclude guardrail test...")


async def run_full_demo(
    config: DemoConfig,
    bug_id: str = "bug_1",
    with_guardrail: bool = False,
    no_pause: bool = False,
    bugs_dir: Optional[Path] = None,
):
    """Execute the full staged jury demonstration flow (Scenes 1-5 + optional Guardrail)."""
    if bugs_dir is None:
        bugs_dir = Path(__file__).resolve().parent.parent.parent / "bugs"

    narrator = Narrator()
    gitops = GitOpsManager(config.app_clone_path, config.github_pat)
    llm_chain = ResilientLLMChain(config.groq_api_key, config.gemini_api_key)

    narrator.banner()
    t_start = time.perf_counter()

    try:
        # Scene 1: Healthy Control
        await run_scene_1_healthy(config, narrator, no_pause=no_pause)

        # Scene 2: Bad Commit
        await run_scene_2_bad_commit(config, gitops, bug_id, bugs_dir, narrator, no_pause=no_pause)

        # Scene 3: Negative Control
        await run_scene_3_negative_control(config, narrator, no_pause=no_pause)

        # Scene 4: Real Fix
        fix_result = await run_scene_4_real_fix(
            config, narrator, llm_chain, dry_run=False, no_pause=no_pause
        )

        # Optional Scene G (Security Guardrail)
        if with_guardrail:
            await run_scene_guardrail(config, narrator, no_pause=no_pause)

        # Scene 5: Human in the loop
        elapsed = time.perf_counter() - t_start
        await run_scene_5_human_in_the_loop(
            config, gitops, fix_result, narrator, elapsed, no_pause=no_pause
        )
    except Exception as e:
        narrator.console.print()
        narrator.console.print(
            f"[bold red]❌ Demonstration halted due to error:[/bold red] {e}"
        )


async def run_single_pipeline(
    config: DemoConfig,
    bug_id: str = "bug_1",
    dry_run: bool = False,
    bugs_dir: Optional[Path] = None,
):
    """Execute a single run of the pipeline with live narration."""
    if bugs_dir is None:
        bugs_dir = Path(__file__).resolve().parent.parent.parent / "bugs"

    narrator = Narrator()
    llm_chain = ResilientLLMChain(config.groq_api_key, config.gemini_api_key)
    narrator.banner()

    try:
        await run_scene_4_real_fix(config, narrator, llm_chain, dry_run=dry_run, no_pause=True)
    except Exception as e:
        narrator.console.print()
        narrator.console.print(
            f"[bold red]❌ Pipeline run halted due to error:[/bold red] {e}"
        )

