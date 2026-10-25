"""Bug triage, deduplication, error signatures, and assertion failure classification."""

import hashlib
import re
from typing import Dict, List, Optional

from kawach.core.logging import ANSI_REGEX
from kawach.execution.exploratory import emit_minimal_repro_script, shrink_failing_path
from kawach.schemas import Bug, BugsFile, Catalog, Evidence, Results, RunInput
from kawach.storage import artifacts as storage


def clean_error_message(msg: Optional[str]) -> str:
    """Strip ANSI escape codes and leading/trailing whitespace."""
    if not msg:
        return ""
    return ANSI_REGEX.sub("", msg).strip()


def is_assertion_failure(error_message: str) -> bool:
    r"""Return True if the error matches an assertion failure and is not a script, locator, or timeout error."""
    if not error_message:
        return False
    cleaned = clean_error_message(error_message)
    if cleaned.startswith("Test timeout of"):
        return False

    cleaned_lower = cleaned.lower()

    # Script / locator action errors are NOT assertion failures (Phase 3 requirements)
    script_error_markers = [
        "strict mode violation",
        "timeouterror: locator.",
        "locator.click: timeout",
        "locator.fill: timeout",
        "locator.selectoption: timeout",
        "locator.hover: timeout",
        "locator.check: timeout",
        "locator.waitfor: timeout",
        "locator.press: timeout",
        "target page, context or browser has been closed",
    ]
    if any(marker in cleaned_lower for marker in script_error_markers):
        return False

    # Extract header lines before any code frame snippets (which start with '12 |' or '> 12 |')
    lines = cleaned.split("\n")
    header_lines = []
    for line in lines:
        if re.match(r"^\s*>?\s*\d+\s*\|", line):
            break
        header_lines.append(line)
    header = "\n".join(header_lines)

    # Check for expect/assertion patterns in the header error
    if re.search(r"expect(\.poll)?\(.*?\)\.(not\.)?to\w+", header, re.DOTALL):
        return True
    if "assertionerror" in header.lower():
        return True
    if re.search(r"error:\s*expect\(", header, re.IGNORECASE):
        return True
    if re.search(r"timed out \d+ms waiting for expect\(", header, re.IGNORECASE):
        return True
    if "expected error feedback" in header.lower() or "expected success feedback" in header.lower():
        return True

    return False


def signature(error_message: str) -> str:
    """Compute 10-hex SHA1 error signature following CONTRACTS.md Section 9.

    Take first 400 characters of cleaned message,
    replace runs of 4+ digits with 'N',
    replace patterns like [a-z]+-\\d{13}-[a-z0-9]{4} with 'U',
    collapse whitespace, lower-case, sha1 and keep 10 hex characters.
    """
    cleaned = clean_error_message(error_message)[:400]
    cleaned = re.sub(r"[a-z]+-\d{13}-[a-z0-9]{4}", "U", cleaned)
    cleaned = re.sub(r"\d{4,}", "N", cleaned)
    cleaned = " ".join(cleaned.split()).lower()
    return hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:10]


def triage(run_id: str) -> List[Bug]:
    """Triage test results into assertion failures and de-duplicate by (failing state, symptom signature)."""
    results_obj = storage.load_model(run_id, "results.json", Results)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    run_input = storage.load_model(run_id, "input.json", RunInput)
    base_url = run_input.targetUrl if run_input else "http://localhost:4000"

    catalog_map = {t.id: t for t in catalog.tests} if catalog else {}

    r_dir = storage.run_dir(run_id)
    candidate_failures = [
        t for t in (results_obj.tests if results_obj else [])
        if t.outcome in ("assertion_failure", "failed", "passed_with_issues")
    ]

    candidate_bugs: List[Bug] = []

    for t in candidate_failures:
        test_case = catalog_map.get(t.testId)
        title = test_case.title if test_case else t.title
        spec_ref = test_case.specRef if test_case else []
        steps = [s.action for s in test_case.steps] if test_case else []
        depth = test_case.depth if test_case else (t.depth or 1)

        expected = ""
        if test_case and test_case.steps:
            for s in reversed(test_case.steps):
                if s.expected:
                    expected = s.expected
                    break

        cleaned_err = clean_error_message(t.errorMessage or "")
        first_line = cleaned_err.split("\n")[0] if cleaned_err else ""
        err_sig = signature(cleaned_err)

        # Checkpoint information
        checkpoint = t.checkpoint
        if not checkpoint and test_case and test_case.steps:
            chk_idx = (t.failedStep - 1) if (t.failedStep and 1 <= t.failedStep <= len(test_case.steps)) else -1
            checkpoint = test_case.steps[chk_idx].checkpoint

        # Failing state determination for deduplication:
        failing_state = "root"
        if test_case and test_case.coverageRef:
            failing_state = test_case.coverageRef[0]
        elif checkpoint:
            failing_state = checkpoint
        else:
            url_match = re.search(r"(/[a-zA-Z0-9_\-\./]*)", t.title + " " + cleaned_err)
            if url_match:
                failing_state = url_match.group(1)

        # Check evidence files
        ev_dir = r_dir / "evidence" / t.testId
        ev_obj = Evidence(
            screenshot=f"evidence/{t.testId}/screenshot.png" if (ev_dir / "screenshot.png").exists() else None,
            video=f"evidence/{t.testId}/video.webm" if (ev_dir / "video.webm").exists() else None,
            trace=f"evidence/{t.testId}/trace.zip" if (ev_dir / "trace.zip").exists() else None,
            console=f"evidence/{t.testId}/console.json" if (ev_dir / "console.json").exists() else None,
            network=f"evidence/{t.testId}/network.json" if (ev_dir / "network.json").exists() else None,
        )

        category: str = "other"
        severity: str = "medium"
        if t.outcome == "passed_with_issues":
            if getattr(t, "failureType", None) == "server_error_5xx":
                category = "network"
                severity = "high"
            else:
                category = "console"
                severity = "medium"
        elif any(k in title.lower() for k in ("login", "auth", "credential", "password", "signup")):
            category = "auth"
            severity = "high"
        elif any(k in title.lower() for k in ("cart", "checkout", "total", "price", "order")):
            category = "data"
            severity = "high"

        # Minimal path shrinking
        shrunk_path = shrink_failing_path(steps, t.failedStep)

        candidate_bugs.append(
            Bug(
                id="",
                testId=t.testId,
                source=t.source,
                title=title,
                grep=f"{t.testId}:",
                file=f"scripts/{t.testId}.spec.ts",
                category=category,  # type: ignore
                severity=severity,  # type: ignore
                specRef=spec_ref,
                steps=steps,
                expected=expected or "Operation completes successfully without errors",
                actual=first_line,
                errorMessage=cleaned_err[:3000],
                signature=f"{failing_state}::{err_sig}",
                duplicates=[],
                evidence=ev_obj,
                status="candidate",
                replay=None,
                depth=depth,
                failingPath=shrunk_path,
                checkpoint=checkpoint,
                provenance={
                    "runId": run_id,
                    "testId": t.testId,
                    "targetUrl": base_url,
                    "outcome": t.outcome,
                    "failureType": getattr(t, "failureType", None),
                },
            )
        )

    # De-duplicate by compound key: (failing state, symptom signature)
    seen_sigs: Dict[str, Bug] = {}
    unique_bugs: List[Bug] = []

    for b in candidate_bugs:
        if b.signature in seen_sigs:
            seen_sigs[b.signature].duplicates.append(b.testId)
        else:
            seen_sigs[b.signature] = b
            unique_bugs.append(b)

    # Assign IDs B01, B02, ... and emit minimal reproduction scripts
    repro_dir = r_dir / "repro"
    for idx, b in enumerate(unique_bugs, start=1):
        b.id = f"B{idx:02d}"
        try:
            repro_file = emit_minimal_repro_script(
                bug_id=b.id,
                title=b.title,
                base_url=base_url,
                steps=b.failingPath,
                out_dir=repro_dir,
            )
            b.reproductionScript = f"repro/{repro_file.name}"
        except Exception:
            pass

    bugs_file = BugsFile(runId=run_id, bugs=unique_bugs)
    storage.save_model(run_id, "bugs.json", bugs_file)
    return unique_bugs
