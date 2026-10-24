"""Thread-safe file-backed storage for runs, metadata, and artifacts."""

import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from kawach.core.clock import now_iso
from kawach.core.config import settings
from kawach.core.ids import new_run_id
from kawach.schemas import (
    AppMap,
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


def run_dir(run_id: str) -> Path:
    """Return the absolute path of the run folder, creating it on demand.
    
    Checks both settings.runs_dir and demo-data/golden for runs.
    """
    path = (settings.runs_dir / run_id).resolve()
    if (path / "run.json").exists():
        return path
    golden = (settings.repo_root / "demo-data" / "golden" / run_id).resolve()
    if (golden / "run.json").exists():
        return golden
    golden_dir = settings.repo_root / "demo-data" / "golden"
    if golden_dir.exists():
        for g_entry in golden_dir.iterdir():
            if g_entry.is_dir() and (g_entry / "run.json").exists():
                try:
                    with open(g_entry / "run.json", "r", encoding="utf-8") as f:
                        r_data = json.load(f)
                        if r_data.get("runId") == run_id:
                            return g_entry.resolve()
                except Exception:
                    pass
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(run_id: str, rel: str) -> Optional[Any]:
    """Read and parse a JSON file relative to the run directory. Return None if missing."""
    file_path = run_dir(run_id) / rel
    if not file_path.exists():
        return None
    for attempt in range(5):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, OSError):
            time.sleep(0.02 * (attempt + 1))
        except Exception:
            return None
    return None


def write_json(run_id: str, rel: str, data: Any) -> None:
    """Atomically write JSON data to rel inside run_id directory with Windows retry/fallback."""
    target_path = run_dir(run_id) / rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + f".tmp.{secrets.token_hex(4)}")

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        # Direct fallback write
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return

    # Windows file replacement retry loop to protect against reader contention and indexing
    replaced = False
    for attempt in range(10):
        try:
            os.replace(temp_path, target_path)
            replaced = True
            break
        except (PermissionError, OSError):
            time.sleep(0.04 * (attempt + 1))

    if not replaced:
        # Fallback to direct overwrite if Windows exclusively locked atomic replace
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass


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

        run_data["updatedAt"] = now_iso()
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
        now = now_iso()

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
        run.updatedAt = now_iso()
        save_model(run_id, "run.json", run)
        return run


def list_runs() -> List[RunListItem]:
    """List past runs newest first, populating test/bug counts from catalog and bugs.json."""
    items: List[RunListItem] = []
    scan_dirs = []
    if settings.runs_dir.exists():
        scan_dirs.append(settings.runs_dir)
    golden_dir = settings.repo_root / "demo-data" / "golden"
    if golden_dir.exists():
        scan_dirs.append(golden_dir)

    seen_ids = set()
    for s_dir in scan_dirs:
        for entry in s_dir.iterdir():
            if not entry.is_dir() or entry.name in seen_ids:
                continue
            run_file = entry / "run.json"
            if not run_file.exists():
                continue
            seen_ids.add(entry.name)

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
                        runId=entry.name,
                        createdAt=run.createdAt,
                        stage=run.stage,
                        mode=run.mode,
                        targetUrl=run.targetUrl,
                        counts=counts,
                    )
                )
            except Exception:
                continue

    items.sort(key=lambda x: x.createdAt, reverse=True)
    return items


# In-memory recent events log per run for polling fallback (run_id -> list of {id, data})
RUN_EVENTS_CACHE: Dict[str, List[Dict[str, str]]] = {}

# In-memory streaming logs cache per run (run_id -> list of log entry dicts)
RUN_LOGS_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def record_event(run_id: str, event_dict: dict) -> None:
    """Record an SSE event into memory cache."""
    with _lock:
        if run_id not in RUN_EVENTS_CACHE:
            RUN_EVENTS_CACHE[run_id] = []
        RUN_EVENTS_CACHE[run_id].append({
            "id": f"ev_{int(time.time()*1000)}_{len(RUN_EVENTS_CACHE[run_id])}",
            "data": json.dumps(event_dict),
        })
        if len(RUN_EVENTS_CACHE[run_id]) > 200:
            RUN_EVENTS_CACHE[run_id] = RUN_EVENTS_CACHE[run_id][-200:]


def log_pipeline(run_id: str, message: str, level: str = "info", source: str = "pipeline") -> dict:
    """Thread-safe logging helper for background agent tasks and Playwright runner."""
    with _lock:
        if run_id not in RUN_LOGS_CACHE:
            RUN_LOGS_CACHE[run_id] = []

        entry = {
            "id": f"{int(time.time()*1000)}-{secrets.token_hex(2)}",
            "timestamp": now_iso(),
            "level": level,
            "source": source,
            "message": message,
        }
        RUN_LOGS_CACHE[run_id].append(entry)
        if len(RUN_LOGS_CACHE[run_id]) > 500:
            RUN_LOGS_CACHE[run_id] = RUN_LOGS_CACHE[run_id][-500:]

        record_event(run_id, {"type": "log", **entry})

    try:
        rdir = run_dir(run_id)
        if rdir.exists():
            with open(rdir / "pipeline.log", "a", encoding="utf-8") as f:
                f.write(f"[{entry['timestamp']}] [{level.upper()}] [{source}] {message}\n")
    except Exception:
        pass

    return entry


def get_run_logs(run_id: str) -> List[Dict[str, Any]]:
    """Return all logs recorded for a run."""
    with _lock:
        logs = list(RUN_LOGS_CACHE.get(run_id, []))
    if not logs:
        pipeline_file = run_dir(run_id) / "pipeline.log"
        if pipeline_file.exists():
            try:
                with open(pipeline_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            logs.append({
                                "id": secrets.token_hex(4),
                                "timestamp": now_iso(),
                                "level": "info",
                                "source": "pipeline",
                                "message": line,
                            })
            except Exception:
                pass
    return logs


def get_run_events(run_id: str) -> List[Dict[str, str]]:
    """Return recent events for a run."""
    with _lock:
        return list(RUN_EVENTS_CACHE.get(run_id, []))
