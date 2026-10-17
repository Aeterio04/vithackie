"""Thread-safe file-backed storage for runs, metadata, and artifacts."""

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from app.config import settings
from app.models import (
    BugsFile,
    Catalog,
    Progress,
    Run,
    RunListItem,
    RunListItemCounts,
    Stage,
    StageTime,
)

_lock = threading.RLock()
T = TypeVar("T", bound=BaseModel)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_dir(run_id: str) -> Path:
    """Return the absolute path of the run folder, creating it on demand."""
    path = (settings.runs_dir / run_id).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_run_id() -> str:
    """Generate a run ID in the format YYYYMMDD-HHMMSS-xxxx with 4 hex chars."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rand_hex = secrets.token_hex(2)
    return f"{timestamp}-{rand_hex}"


def read_json(run_id: str, rel: str) -> Optional[Any]:
    """Read and parse a JSON file relative to the run directory. Return None if missing."""
    file_path = run_dir(run_id) / rel
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json(run_id: str, rel: str, data: Any) -> None:
    """Atomically write JSON data to rel inside run_id directory using a temp file."""
    target_path = run_dir(run_id) / rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + f".tmp.{secrets.token_hex(4)}")

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_path, target_path)


def load_model(run_id: str, rel: str, model_cls: Type[T]) -> Optional[T]:
    """Load and validate a Pydantic model from a JSON file in the run directory."""
    data = read_json(run_id, rel)
    if data is None:
        return None
    return model_cls.model_validate(data)


def save_model(run_id: str, rel: str, obj: BaseModel) -> None:
    """Serialize and atomically save a Pydantic model to a JSON file in the run directory."""
    data = obj.model_dump(by_alias=True, mode="json")
    write_json(run_id, rel, data)


def get_run(run_id: str) -> Run:
    """Load and return the Run model for the given run_id."""
    with _lock:
        run = load_model(run_id, "run.json", Run)
        if run is None:
            raise FileNotFoundError(f"Run {run_id} run.json not found")
        return run


def update_run(run_id: str, **fields: Any) -> Run:
    """Update fields on run.json with thread-safe read-modify-write and bump updatedAt."""
    with _lock:
        run = get_run(run_id)
        run_data = run.model_dump(by_alias=True)

        for key, value in fields.items():
            if key == "progress" and isinstance(value, dict):
                run_data["progress"] = value
            elif key == "stageTimes" and isinstance(value, dict):
                run_data["stageTimes"] = value
            else:
                run_data[key] = value

        run_data["updatedAt"] = _now_iso()
        updated_run = Run.model_validate(run_data)
        save_model(run_id, "run.json", updated_run)
        return updated_run


def set_stage(
    run_id: str,
    stage: Stage,
    step: Optional[str] = None,
    done: int = 0,
    total: int = 0,
) -> Run:
    """Update the stage of a run, maintaining stageTimes (startedAt/endedAt) and progress."""
    with _lock:
        run = get_run(run_id)
        now = _now_iso()

        # Update previous stage endedAt if it was active
        prev_stage = run.stage
        if prev_stage in run.stageTimes:
            prev_time = run.stageTimes[prev_stage]
            if prev_time.endedAt is None:
                run.stageTimes[prev_stage] = StageTime(
                    startedAt=prev_time.startedAt, endedAt=now
                )

        # Set or update current stage times
        if stage in run.stageTimes:
            curr_start = run.stageTimes[stage].startedAt or now
            run.stageTimes[stage] = StageTime(
                startedAt=curr_start,
                endedAt=now if stage in ("done", "failed") else None,
            )
        else:
            run.stageTimes[stage] = StageTime(
                startedAt=now,
                endedAt=now if stage in ("done", "failed") else None,
            )

        run.stage = stage
        run.updatedAt = now

        if step is not None:
            run.progress = Progress(step=step, done=done, total=total)
        else:
            run.progress = None

        save_model(run_id, "run.json", run)
        return run


def fail_run(run_id: str, message: str) -> Run:
    """Mark a run as failed, record the error message, and update stageTimes."""
    with _lock:
        run = set_stage(run_id, "failed")
        run.error = message
        run.updatedAt = _now_iso()
        save_model(run_id, "run.json", run)
        return run


def read_secret_password(run_id: str) -> str:
    """Read the test password from secrets.json without leaking it to logs or models."""
    data = read_json(run_id, "secrets.json")
    if isinstance(data, dict):
        return str(data.get("password", ""))
    return ""


def list_runs() -> List[RunListItem]:
    """List past runs newest first, populating test/bug counts from catalog and bugs.json."""
    items: List[RunListItem] = []
    if not settings.runs_dir.exists():
        return items

    for entry in settings.runs_dir.iterdir():
        if not entry.is_dir():
            continue
        run_file = entry / "run.json"
        if not run_file.exists():
            continue

        try:
            run = load_model(entry.name, "run.json", Run)
            if run is None:
                continue

            tests_count = 0
            cat = load_model(entry.name, "catalog.json", Catalog)
            if cat is not None:
                tests_count = len(cat.tests)

            bugs_count = 0
            confirmed_count = 0
            flaky_count = 0
            bugs_file = load_model(entry.name, "bugs.json", BugsFile)
            if bugs_file is not None:
                bugs_count = len(bugs_file.bugs)
                confirmed_count = sum(1 for b in bugs_file.bugs if b.status == "confirmed")
                flaky_count = sum(1 for b in bugs_file.bugs if b.status == "flaky")

            counts = RunListItemCounts(
                tests=tests_count,
                bugs=bugs_count,
                confirmed=confirmed_count,
                flaky=flaky_count,
            )
            items.append(
                RunListItem(
                    runId=run.runId,
                    createdAt=run.createdAt,
                    stage=run.stage,
                    mode=run.mode,
                    targetUrl=run.targetUrl,
                    counts=counts,
                )
            )
        except Exception:
            continue

    # Newest first by createdAt descending
    items.sort(key=lambda x: x.createdAt, reverse=True)
    return items
