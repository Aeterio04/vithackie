"""Bug verification module that performs 3 deterministic replays per candidate.

Implemented by Track C.
"""

from typing import List
from app.models import Verification


def verify_bug(run_id: str, bug_id: str) -> Verification:
    """Replay a bug candidate 3 times to determine if confirmed, flaky, or not reproduced.

    Implemented by Track C.
    """
    raise NotImplementedError("Track C implements verify_bug")


def verify_all(run_id: str) -> List[Verification]:
    """Verify all candidate bugs in a run and return their verification records.

    Implemented by Track C.
    """
    raise NotImplementedError("Track C implements verify_all")
