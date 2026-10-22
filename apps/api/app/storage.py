"""Backwards compatibility shim forwarding to kawach.storage."""

from kawach.core.clock import now_iso as _now_iso
from kawach.core.config import settings
from kawach.storage.artifacts import (
    _lock,
    fail_run,
    get_run,
    list_runs,
    load_model,
    new_run_id,
    read_json,
    run_dir,
    save_model,
    set_stage,
    update_run,
    write_json,
)
from kawach.storage.secrets import (
    read_secret_password,
    write_secret_password,
)

__all__ = [
    "run_dir",
    "new_run_id",
    "save_model",
    "load_model",
    "read_json",
    "write_json",
    "get_run",
    "update_run",
    "set_stage",
    "fail_run",
    "list_runs",
    "read_secret_password",
    "write_secret_password",
    "settings",
    "_lock",
    "_now_iso",
]
