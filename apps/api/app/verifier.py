"""Bug verification module that performs 3 deterministic replays per candidate."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import List, Optional

from app.config import settings
from app.models import (
    Bug,
    BugReplay,
    BugsFile,
    Outcome,
    Progress,
    Verification,
    VerificationAttempt,
)
from app import runner_client
from app import storage

_bugs_lock = threading.RLock()


def _first_line(msg: Optional[str]) -> str:
    if not msg:
        return ""
    lines = msg.strip().split("\n")
    return lines[0].strip() if lines else ""


def verify_bug(run_id: str, bug_id: str) -> Verification:
    """Replay a bug candidate 3 times to determine if confirmed, flaky, or not reproduced."""
    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
    if not bugs_file or not bugs_file.bugs:
        raise ValueError(f"No bugs found in run {run_id}")

    target_bug: Optional[Bug] = None
    for b in bugs_file.bugs:
        if b.id == bug_id:
            target_bug = b
            break

    if target_bug is None:
        raise ValueError(f"Bug {bug_id} not found in run {run_id}")

    r_dir = storage.run_dir(run_id)

    # Determine spec_dir and extra_env
    if target_bug.file.startswith("probes/"):
        spec_dir = str(settings.repo_root / "runner" / "probes")
        extra_env = {"APP_MAP_PATH": str(r_dir / "app_map.json")}
    else:
        bug_file_path = r_dir / target_bug.file
        spec_dir = str(bug_file_path.parent)
        extra_env = None

    try:
        from app.frontend_adapter import log_pipeline
    except Exception:
        def log_pipeline(*args, **kwargs): pass

    attempts: List[VerificationAttempt] = []

    for attempt_num in range(1, 4):
        storage.update_run(
            run_id,
            progress=Progress(
                step=f"Replaying {target_bug.id} (attempt {attempt_num}/3)",
                done=attempt_num - 1,
                total=3,
            ),
        )
        log_pipeline(
            run_id,
            f"Deterministic Verifier: Replaying suspected defect {target_bug.id} ({target_bug.title}) - Trial {attempt_num}/3...",
            source="verifier",
        )

        out_name = f"verify/{target_bug.id}/{attempt_num}"
        raw_run = runner_client.run_playwright(
            run_id,
            files=[target_bug.file],
            grep=target_bug.grep,
            workers=1,
            out_name=out_name,
            spec_dir=spec_dir,
            extra_env=extra_env,
        )

        outcome: Outcome = "test_error"
        reproduced = False
        err_msg: Optional[str] = None
        duration_ms = int(raw_run.duration_s * 1000)

        if raw_run.report_path:
            records = runner_client.parse_report(raw_run.report_path)
            matching = [
                r for r in records
                if r.get("title", "").startswith(target_bug.grep) or target_bug.grep in r.get("title", "")
            ]

            if matching:
                rec = matching[0]
                status = rec.get("status")
                rec_err = runner_client.clean_error_message(rec.get("errorMessage", ""))
                duration_ms = rec.get("durationMs", duration_ms)
                err_msg = rec_err[:500] if rec_err else None

                if status == "passed":
                    outcome = "passed"
                    reproduced = False
                elif runner_client.is_assertion_failure(rec_err):
                    outcome = "assertion_failure"
                    # Compare signature or first line
                    rec_sig = runner_client.signature(rec_err)
                    sig_match = rec_sig == target_bug.signature
                    first_line_match = _first_line(rec_err) == _first_line(target_bug.errorMessage)
                    reproduced = sig_match or first_line_match
                else:
                    outcome = "test_error"
                    reproduced = False
            else:
                err_msg = f"No matching test record for grep {target_bug.grep}"
        else:
            err_msg = f"Playwright failed: {raw_run.stderr[:500]}"

        attempts.append(
            VerificationAttempt(
                attempt=attempt_num,
                reproduced=reproduced,
                outcome=outcome,
                errorMessage=err_msg,
                durationMs=duration_ms,
            )
        )

    reproduced_count = sum(1 for a in attempts if a.reproduced)
    if reproduced_count == 3:
        status = "confirmed"
    elif reproduced_count in (1, 2):
        status = "flaky"
    else:
        status = "not_reproduced"

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    verification = Verification(
        bugId=target_bug.id,
        verifiedAt=now_iso,
        attempts=attempts,
        reproduced=reproduced_count,
        status=status,
    )

    # Save verification file
    v_dir = r_dir / "verification"
    v_dir.mkdir(parents=True, exist_ok=True)
    storage.save_model(run_id, f"verification/{target_bug.id}.json", verification)

    # Update bugs.json under lock
    with _bugs_lock:
        latest_bugs = storage.load_model(run_id, "bugs.json", BugsFile)
        if latest_bugs:
            for b in latest_bugs.bugs:
                if b.id == target_bug.id:
                    b.status = status
                    b.replay = BugReplay(reproduced=reproduced_count, attempts=3)
                    break
            storage.save_model(run_id, "bugs.json", latest_bugs)

    return verification


def verify_all(run_id: str) -> List[Verification]:
    """Verify all candidate bugs in a run and return their verification records."""
    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
    if not bugs_file or not bugs_file.bugs:
        return []

    bugs = bugs_file.bugs
    storage.set_stage(
        run_id,
        "verifying",
        step="Replaying bugs",
        done=0,
        total=len(bugs),
    )

    results: List[Verification] = []

    parallel_workers = getattr(settings, "VERIFY_PARALLEL", 1)
    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            future_to_bug = {
                executor.submit(verify_bug, run_id, b.id): b.id for b in bugs
            }
            done_count = 0
            for fut in future_to_bug:
                res = fut.result()
                results.append(res)
                done_count += 1
                storage.update_run(
                    run_id,
                    progress=Progress(
                        step="Replaying bugs",
                        done=done_count,
                        total=len(bugs),
                    ),
                )
    else:
        for idx, b in enumerate(bugs, start=1):
            res = verify_bug(run_id, b.id)
            results.append(res)
            storage.update_run(
                run_id,
                progress=Progress(
                    step=f"Replayed {b.id}",
                    done=idx,
                    total=len(bugs),
                ),
            )

    results.sort(key=lambda v: v.bugId)
    return results
