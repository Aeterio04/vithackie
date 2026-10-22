"""ID generation utilities."""

from datetime import datetime, timezone
import secrets


def new_run_id() -> str:
    """Generate a run ID in the format YYYYMMDD-HHMMSS-xxxx with 4 hex chars."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rand_hex = secrets.token_hex(2)
    return f"{timestamp}-{rand_hex}"


def new_id(prefix: str = "id") -> str:
    """Generate a random unique identifier with the given prefix."""
    rand_hex = secrets.token_hex(4)
    return f"{prefix}_{rand_hex}"
