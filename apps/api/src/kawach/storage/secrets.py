"""Secrets storage for run credentials (passwords, tokens)."""

from typing import Optional
from kawach.core.config import settings


def read_secret_password(run_id: str) -> str:
    """Read the test password from secrets.json without leaking it to logs or models."""
    from kawach.storage.artifacts import read_json
    data = read_json(run_id, "secrets.json")
    if isinstance(data, dict):
        return str(data.get("password", ""))
    return ""


def write_secret_password(run_id: str, password: str) -> None:
    """Write secrets.json containing password for run_id."""
    from kawach.storage.artifacts import write_json
    write_json(run_id, "secrets.json", {"password": password})
