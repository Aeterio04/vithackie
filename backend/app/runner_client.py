"""Subprocess client for the Playwright runner in runner/.

Implemented by Track C.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from app.models import Bug, Results


@dataclass
class RawRun:
    """Raw execution output from a Playwright subprocess run."""

    exit_code: int
    report_path: Optional[str]
    stdout: str
    stderr: str
    duration_s: float


@dataclass
class ListResult:
    """Validation result from playwright test --list."""

    ok: bool
    error: Optional[str] = None


def run_playwright(
    run_id: str,
    *,
    files: Optional[List[str]] = None,
    grep: Optional[str] = None,
    workers: int = 4,
    spec_dir: Optional[str] = None,
    out_name: str = "main",
    extra_env: Optional[Dict[str, str]] = None,
    timeout_s: int = 900,
) -> RawRun:
    """Execute Playwright CLI in runner/ directory with configured environment.

    Implemented by Track C.
    """
    raise NotImplementedError("Track C implements run_playwright")


def list_tests(run_id: str, file: str) -> ListResult:
    """Run playwright test <file> --list to verify script syntax and loadability.

    Implemented by Track C.
    """
    raise NotImplementedError("Track C implements list_tests")


def run_tests(
    run_id: str,
    workers: Optional[int] = None,
    include_probes: bool = False,
) -> Results:
    """Execute test suite against target app, record evidence, and return Results.

    Implemented by Track C.
    """
    raise NotImplementedError("Track C implements run_tests")


def triage(run_id: str) -> List[Bug]:
    """Triage test results into assertion failures (candidates) and test errors.

    Implemented by Track C.
    """
    raise NotImplementedError("Track C implements triage")


def is_assertion_failure(error_message: str) -> bool:
    """Return True if the error matches expect() assertion pattern and is not a timeout.

    Implemented by Track C.
    """
    raise NotImplementedError("Track C implements is_assertion_failure")
