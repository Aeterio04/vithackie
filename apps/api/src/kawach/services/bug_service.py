"""Bug query and retest service."""

from typing import List, Optional

from kawach.execution.verifier import verify_bug
from kawach.schemas import Bug, BugsFile, Verification
from kawach.storage import artifacts as storage


def get_bugs(run_id: str) -> List[Bug]:
    """Return all bugs found in a run."""
    bugs_file = storage.load_model(run_id, "bugs.json", BugsFile)
    if not bugs_file:
        return []
    return bugs_file.bugs


def get_bug(run_id: str, bug_id: str) -> Optional[Bug]:
    """Retrieve a single bug by its ID."""
    bugs = get_bugs(run_id)
    for b in bugs:
        if b.id == bug_id:
            return b
    return None


def retest_bug(run_id: str, bug_id: str) -> Verification:
    """Execute deterministic 3x replay for a specific bug."""
    return verify_bug(run_id, bug_id)
