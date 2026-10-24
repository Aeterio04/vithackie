"""Verifier agent: deterministically verifies test failures in an isolated environment."""

from typing import List, Optional, Tuple
from kawach_fix.clients.runner import ScriptRunner
from kawach_fix.schemas import FixOptions, FixRequest, FixResult, RunItem, VerificationResult


async def run_verifier(
    request: FixRequest, runner: ScriptRunner
) -> Tuple[VerificationResult, Optional[FixResult]]:
    """Execute the failing test verify_runs times and calculate verdict."""
    opts: FixOptions = request.options
    runs: List[RunItem] = []
    failures = 0
    observed_errors: List[str] = []

    for i in range(1, opts.verify_runs + 1):
        item = await runner.run_test(
            script_path_or_code=request.playwright_script,
            target_url=request.target_url,
            project_dir=request.playwright_project_dir,
            timeout_sec=opts.run_timeout_sec,
            run_index=i,
        )
        runs.append(item)
        if not item.passed:
            failures += 1
            if item.error_text:
                observed_errors.append(item.error_text)

    # Determine verdict
    if failures >= opts.min_failures:
        verdict = "confirmed"
    elif failures > 0:
        verdict = "flaky"
    else:
        verdict = "not_reproduced"

    observed_error = observed_errors[0] if observed_errors else None
    verification = VerificationResult(
        runs=runs,
        failures=failures,
        verdict=verdict,
        observed_error=observed_error,
    )

    early_result: Optional[FixResult] = None
    if verdict == "not_reproduced":
        early_result = FixResult(
            status="not_reproduced",
            reason=f"This error does not exist: script passed {opts.verify_runs}/{opts.verify_runs} runs.",
            verification=verification,
        )
    elif verdict == "flaky":
        early_result = FixResult(
            status="flaky",
            reason=(
                f"Failing test is flaky: failed {failures}/{opts.verify_runs} runs "
                f"(minimum {opts.min_failures} failures required to confirm defect)."
            ),
            verification=verification,
        )

    return verification, early_result
