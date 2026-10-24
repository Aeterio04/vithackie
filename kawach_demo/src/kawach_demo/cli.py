"""Command-Line Interface (CLI) for the Kawach Demo Harness."""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console

from kawach_demo.config import DemoConfig, load_config
from kawach_demo.github_admin import GitHubAdmin
from kawach_demo.gitops import GitOpsManager
from kawach_demo.narrator import Narrator
from kawach_demo.preflight import run_preflight
from kawach_demo.redact import redact_text
from kawach_demo.rehearse import run_rehearsal
from kawach_demo.scenes import load_catalog, run_full_demo, run_single_pipeline

console = Console()


def normalize_bug_arg(raw: str) -> str:
    """Normalize input like '1' or 'bug_1' to 'bug_1'."""
    raw = raw.strip().lower()
    if raw.startswith("bug_"):
        return raw
    return f"bug_{raw}"


def parse_bugs_list(raw: str) -> List[str]:
    """Parse comma-separated bug list like '1,2,3' or 'bug_1,bug_2'."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return [normalize_bug_arg(p) for p in parts]


def get_bugs_dir() -> Path:
    """Resolve path to bugs directory."""
    return Path(__file__).resolve().parent.parent.parent / "bugs"


async def handle_preflight(config: DemoConfig) -> int:
    """Handle preflight command."""
    ok = await run_preflight(config)
    return 0 if ok else 1


async def handle_reset(config: DemoConfig) -> int:
    """Handle reset command: close PRs, delete branches, reset repo to demo-good."""
    admin = GitHubAdmin(config.github_pat, config.demo_repo)
    gitops = GitOpsManager(config.app_clone_path, config.github_pat)

    console.print("\n[bold cyan]🧹 Starting Kawach Demo Reset...[/bold cyan]")

    console.print("  [dim]• Closing open kawach/fix-* pull requests...[/dim]")
    closed = await admin.close_open_fix_prs()
    console.print(f"    [green]✓ Closed {len(closed)} pull request(s)[/green]")

    console.print("  [dim]• Deleting remote kawach/fix-* branches...[/dim]")
    deleted = await admin.delete_fix_branches()
    console.print(f"    [green]✓ Deleted {len(deleted)} remote branch(es)[/green]")

    console.print("  [dim]• Resetting local clone and origin/main to 'demo-good'...[/dim]")
    gitops.reset_to_tag("demo-good")
    gitops.pull()
    console.print("    [green]✓ Clone and origin/main synchronized at tag 'demo-good'[/green]\n")

    console.print("[bold green]✓ Reset successfully finished.[/bold green]\n")
    return 0


def handle_plant_bug(config: DemoConfig, bug_id: str) -> int:
    """Handle plant-bug command."""
    gitops = GitOpsManager(config.app_clone_path, config.github_pat)
    bugs_dir = get_bugs_dir()
    catalog = load_catalog(bugs_dir / "catalog.json")

    if bug_id not in catalog:
        console.print(f"[bold red]Unknown bug ID '{bug_id}'. Available: {list(catalog.keys())}[/bold red]")
        return 1

    patch_file = bugs_dir / f"{bug_id}.patch"
    commit_msg = catalog[bug_id]["commit_message"]

    console.print(f"\n[bold yellow]🌱 Planting {bug_id}...[/bold yellow]")
    console.print(f"  [dim]Commit message: '{commit_msg}'[/dim]")
    sha = gitops.plant_bug(patch_file, commit_msg)
    console.print(f"[bold green]✓ Successfully planted and pushed commit:[/bold green] [bold cyan]{sha[:8]}[/bold cyan] ({sha})\n")
    return 0


async def handle_run(config: DemoConfig, bug_id: str, dry_run: bool) -> int:
    """Handle run command: execute pipeline once."""
    await run_single_pipeline(config, bug_id=bug_id, dry_run=dry_run, bugs_dir=get_bugs_dir())
    return 0


async def handle_rehearse(config: DemoConfig, bugs: List[str], repetitions: int) -> int:
    """Handle rehearse command."""
    gitops = GitOpsManager(config.app_clone_path, config.github_pat)
    narrator = Narrator()
    await run_rehearsal(
        config=config,
        gitops=gitops,
        bugs=bugs,
        repetitions=repetitions,
        bugs_dir=get_bugs_dir(),
        narrator=narrator,
    )
    return 0


async def handle_full(
    config: DemoConfig,
    bug_id: str,
    with_guardrail: bool,
    no_pause: bool,
) -> int:
    """Handle full staged jury demo command."""
    await run_full_demo(
        config=config,
        bug_id=bug_id,
        with_guardrail=with_guardrail,
        no_pause=no_pause,
        bugs_dir=get_bugs_dir(),
    )
    return 0


def main(argv: List[str] = None) -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="python -m kawach_demo",
        description="Kawach Autonomous Fix Pipeline Demonstration Harness",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: preflight
    subparsers.add_parser("preflight", help="Run preflight checks across environment, app, LLM, and GitHub")

    # Subcommand: reset
    subparsers.add_parser("reset", help="Clean up PRs, delete branches, and reset repo to demo-good")

    # Subcommand: plant-bug
    p_plant = subparsers.add_parser("plant-bug", help="Plant a bug patch commit and push to origin main")
    p_plant.add_argument("--bug", default="1", help="Bug ID (e.g. 1, 2, 3 or bug_1)")

    # Subcommand: run
    p_run = subparsers.add_parser("run", help="Run the real pipeline once with live narration")
    p_run.add_argument("--bug", default="1", help="Bug ID to run against")
    p_run.add_argument("--dry-run", action="store_true", help="Synthesize fix without opening PR")

    # Subcommand: rehearse
    p_rehearse = subparsers.add_parser("rehearse", help="Run automated rehearsal matrix across bugs")
    p_rehearse.add_argument("--bugs", default="1,2,3", help="Comma-separated bug list (e.g. 1,2,3)")
    p_rehearse.add_argument("--times", type=int, default=3, help="Number of repetitions per bug")

    # Subcommand: full
    p_full = subparsers.add_parser("full", help="Run the full 5-scene jury presentation demo")
    p_full.add_argument("--bug", default="1", help="Bug ID for demonstration (default: 1)")
    p_full.add_argument("--with-guardrail-scene", action="store_true", help="Include Scene G (Adversarial simulation)")
    p_full.add_argument("--no-pause", action="store_true", help="Skip presenter pauses between scenes")

    args = parser.parse_args(argv)

    try:
        config = load_config()
    except Exception as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        return 1

    secrets = [s.get_secret_value() for s in config.secrets_list]

    try:
        if args.command == "preflight":
            return asyncio.run(handle_preflight(config))
        elif args.command == "reset":
            return asyncio.run(handle_reset(config))
        elif args.command == "plant-bug":
            bug_id = normalize_bug_arg(args.bug)
            return handle_plant_bug(config, bug_id)
        elif args.command == "run":
            bug_id = normalize_bug_arg(args.bug)
            return asyncio.run(handle_run(config, bug_id, args.dry_run))
        elif args.command == "rehearse":
            bugs = parse_bugs_list(args.bugs)
            return asyncio.run(handle_rehearse(config, bugs, args.times))
        elif args.command == "full":
            bug_id = normalize_bug_arg(args.bug)
            return asyncio.run(handle_full(config, bug_id, args.with_guardrail_scene, args.no_pause))
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Execution interrupted by user.[/yellow]")
        return 130
    except Exception as e:
        redacted = redact_text(str(e), secrets)
        console.print(f"[bold red]Unexpected error:[/bold red] {redacted}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
