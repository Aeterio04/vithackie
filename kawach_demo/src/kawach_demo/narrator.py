"""Clean terminal narration for demo and rehearsal flows."""

import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kawach_demo.redact import redact_text


def format_playwright_error(raw_err: Optional[str]) -> str:
    """Extract a concise one-line summary from Playwright assertion errors."""
    if not raw_err:
        return "Unknown error"

    # Match Expected / Received patterns
    expected_m = re.search(r"Expected:\s*([^\n\r]+)", raw_err)
    received_m = re.search(r"Received:\s*([^\n\r]+)", raw_err)
    locator_m = re.search(r"Locator:\s*([^\n\r]+)", raw_err)

    if expected_m and received_m:
        loc = locator_m.group(1).strip() if locator_m else "element"
        exp = expected_m.group(1).strip()
        rec = received_m.group(1).strip()
        return f"{loc} expected {exp}, received {rec}"

    if "Test timeout" in raw_err:
        return "Test timeout exceeded"

    # Fallback to first non-empty line
    lines = [line.strip() for line in raw_err.splitlines() if line.strip()]
    if lines:
        return lines[0][:100]
    return raw_err[:100]


class Narrator:
    """Presentation narrator formatting pipeline events into clear terminal views."""

    def __init__(self, extra_secrets: Optional[Sequence[Any]] = None):
        self.console = Console(highlight=False)
        self.extra_secrets = list(extra_secrets or [])

    def _redact(self, text: str) -> str:
        return redact_text(str(text), self.extra_secrets)

    def print_banner(self):
        banner_text = Text()
        banner_text.append("KAWACH AUTONOMOUS QA FIX PIPELINE\n", style="bold red")
        banner_text.append("Defect Verification, Root-Cause Analysis & GitHub PR Repair", style="white")
        self.console.print(Panel(banner_text, border_style="red", padding=(1, 2)))

    banner = print_banner

    def scene_header(self, scene_number: str, title: str, subtitle: str = ""):
        content = Text()
        content.append(f"SCENE {scene_number}: {title.upper()}\n", style="bold cyan")
        if subtitle:
            content.append(f"{subtitle}", style="dim white")
        self.console.print()
        self.console.print(Panel(content, border_style="cyan", padding=(0, 2)))

    def pause_for_presenter(self, prompt: str = "Press [Enter] to continue..."):
        self.console.print()
        self.console.print(f"[bold yellow]> {prompt}[/bold yellow]", end="")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        self.console.print()

    def step(self, label: str, status: str = "running", detail: str = ""):
        redacted_detail = self._redact(detail)
        if status == "running":
            self.console.print(f"  [bold blue][RUNNING][/bold blue] {label} [dim]{redacted_detail}[/dim]")
        elif status == "success":
            self.console.print(f"  [bold green][PASS][/bold green] {label} [white]{redacted_detail}[/white]")
        elif status == "failure":
            self.console.print(f"  [bold red][FAIL][/bold red] {label} [red]{redacted_detail}[/red]")
        elif status == "info":
            self.console.print(f"  [bold cyan][INFO][/bold cyan] {label} [dim]{redacted_detail}[/dim]")

    def on_replay_run(self, index: int, total: int, passed: bool, duration_ms: int, error_text: Optional[str] = None):
        """Format Playwright defect replay run."""
        if passed:
            self.console.print(f"    [dim]Replay {index}/{total}:[/dim] [green]PASS[/green] (passed unexpectedly in {duration_ms}ms)")
        else:
            summary = format_playwright_error(error_text)
            self.console.print(
                f"    [dim]Replay {index}/{total}:[/dim] [bold red]DEFECT REPRODUCED[/bold red] "
                f"({duration_ms / 1000:.1f}s) -> [yellow]{summary}[/yellow]"
            )

    def on_commit_collected(self, sha: str, message: str, author: str, files: List[str]):
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="bold cyan")
        table.add_column("Value", style="white")

        table.add_row("Pinned SHA", f"[yellow]{sha[:7]}[/yellow] ({sha})")
        table.add_row("Author", author)
        table.add_row("Message", self._redact(message))
        table.add_row("Files Touched", ", ".join(files) if files else "(none)")

        self.console.print(Panel(table, title="[bold]Origin/Main Pinned Commit[/bold]", border_style="blue"))

    def on_proposal_generated(self, root_cause: str, explanation: str, confidence: float, edits: List[Any], provider: str = "Groq"):
        content = Text()
        content.append(f"Provider: {provider}  |  Confidence: {confidence * 100:.0f}%\n\n", style="bold magenta")
        content.append("Root Cause Analysis:\n", style="bold yellow")
        content.append(f"{self._redact(root_cause)}\n\n", style="white")
        content.append("Fix Explanation:\n", style="bold green")
        content.append(f"{self._redact(explanation)}\n", style="white")

        self.console.print(Panel(content, title="[bold]Synthesized Code Repair[/bold]", border_style="magenta"))

    def show_diff(self, path: str, old_str: str, new_str: str):
        diff_text = Text()
        diff_text.append(f"--- a/{path}\n", style="bold red")
        diff_text.append(f"+++ b/{path}\n", style="bold green")
        for line in old_str.splitlines():
            diff_text.append(f"- {self._redact(line)}\n", style="red")
        for line in new_str.splitlines():
            diff_text.append(f"+ {self._redact(line)}\n", style="green")

        self.console.print(Panel(diff_text, title=f"[bold]Patch: {path}[/bold]", border_style="yellow"))

    def on_pr_raised(self, number: Optional[int], url: Optional[str], branch: str, title: str):
        content = Text()
        content.append(f"Pull Request: #{number or 'N/A'}\n", style="bold green")
        content.append(f"Title:  {self._redact(title)}\n", style="white")
        content.append(f"Branch: {branch} -> main\n", style="cyan")
        if url:
            content.append(f"URL:    {url}\n", style="bold underline blue")

        self.console.print(Panel(content, title="[bold]GitHub Pull Request Created[/bold]", border_style="green"))

    def show_summary(self, elapsed_sec: float, replays: int, files_count: int, pr_url: Optional[str] = None):
        table = Table(title="Demonstration Summary", border_style="green", padding=(0, 2))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold white")

        table.add_row("Total Time", f"{elapsed_sec:.1f}s")
        table.add_row("Defect Replays", str(replays))
        table.add_row("Files Repaired", str(files_count))
        table.add_row("Pull Request", pr_url or "Dry run / Local only")

        self.console.print()
        self.console.print(table)
        self.console.print()
