"""Bug triage, deduplication, error signatures, and assertion failure classification."""

import hashlib
import re
from typing import Dict, List, Optional

from kawach.core.logging import ANSI_REGEX
from kawach.schemas import Bug, BugsFile, Catalog, Evidence, Results
from kawach.storage import artifacts as storage


def clean_error_message(msg: Optional[str]) -> str:
    """Strip ANSI escape codes and leading/trailing whitespace."""
    if not msg:
        return ""
    return ANSI_REGEX.sub("", msg).strip()


def is_assertion_failure(error_message: str) -> bool:
    r"""Return True if the error matches expect() assertion pattern and is not a timeout.

    Follows CONTRACTS.md Section 9:
    Matches r"expect\(.*?\)\.(not\.)?to\w+" and does NOT begin with "Test timeout of".
    """
    cleaned = clean_error_message(error_message)
    if cleaned.startswith("Test timeout of"):
        return False
    return bool(re.search(r"expect\(.*?\)\.(not\.)?to\w+", cleaned, re.DOTALL))


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
    """Triage test results into assertion failures (candidates) and de-duplicate."""
    results_obj = storage.load_model(run_id, "results.json", Results)
    catalog = storage.load_model(run_id, "catalog.json", Catalog)
    catalog_map = {t.id: t for t in catalog.tests} if catalog else {}

    r_dir = storage.run_dir(run_id)
    candidate_failures = [
        t for t in (results_obj.tests if results_obj else [])
        if t.outcome == "assertion_failure"
    ]

    candidate_bugs: List[Bug] = []

    for t in candidate_failures:
        test_case = catalog_map.get(t.testId)
        title = test_case.title if test_case else t.title
        spec_ref = test_case.specRef if test_case else []
        steps = [s.action for s in test_case.steps] if test_case else []

        expected = ""
        if test_case and test_case.steps:
            for s in reversed(test_case.steps):
                if s.expected:
                    expected = s.expected
                    break

        cleaned_err = clean_error_message(t.errorMessage or "")
        first_line = cleaned_err.split("\n")[0] if cleaned_err else ""
        err_sig = signature(cleaned_err)

        # Check evidence files
        ev_dir = r_dir / "evidence" / t.testId
        ev_obj = Evidence(
            screenshot=f"evidence/{t.testId}/screenshot.png" if (ev_dir / "screenshot.png").exists() else None,
            video=f"evidence/{t.testId}/video.webm" if (ev_dir / "video.webm").exists() else None,
            trace=f"evidence/{t.testId}/trace.zip" if (ev_dir / "trace.zip").exists() else None,
            console=f"evidence/{t.testId}/console.json" if (ev_dir / "console.json").exists() else None,
            network=f"evidence/{t.testId}/network.json" if (ev_dir / "network.json").exists() else None,
        )

        candidate_bugs.append(
            Bug(
                id="",  # assigned after deduplication
                testId=t.testId,
                source=t.source,
                title=title,
                grep=f"{t.testId}:",
                file=f"scripts/{t.testId}.spec.ts",
                category="other",
                severity="medium",
                specRef=spec_ref,
                steps=steps,
                expected=expected,
                actual=first_line,
                errorMessage=cleaned_err[:3000],
                signature=err_sig,
                duplicates=[],
                evidence=ev_obj,
                status="candidate",
                replay=None,
            )
        )

    # De-duplicate by signature
    seen_sigs: Dict[str, Bug] = {}
    unique_bugs: List[Bug] = []

    for b in candidate_bugs:
        if b.signature in seen_sigs:
            seen_sigs[b.signature].duplicates.append(b.testId)
        else:
            seen_sigs[b.signature] = b
            unique_bugs.append(b)

    # Assign IDs B01, B02, ...
    for idx, b in enumerate(unique_bugs, start=1):
        b.id = f"B{idx:02d}"

    bugs_file = BugsFile(runId=run_id, bugs=unique_bugs)
    storage.save_model(run_id, "bugs.json", bugs_file)
    return unique_bugs
