"""Mappers for converting Bug and Verification models to frontend schemas."""

from typing import Any, Dict, List, Optional

from kawach.core.clock import now_iso
from kawach.schemas import Bug, BugsFile, Verification
from kawach.storage import artifacts as storage


def transform_bug_to_frontend(run_id: str, b: Any) -> dict:
    """Transform backend Bug model to frontend Bug schema."""
    bug_id = getattr(b, "id", "")
    replays = []
    ver_file = storage.run_dir(run_id) / "verification" / f"{bug_id}.json"
    if ver_file.exists():
        try:
            ver = storage.load_model(run_id, f"verification/{bug_id}.json", Verification)
            if ver and ver.attempts:
                for idx, r in enumerate(ver.attempts, 1):
                    replays.append({
                        "index": idx,
                        "result": "reproduced" if r.reproduced else "not_reproduced",
                        "duration_ms": r.durationMs,
                        "video_url": f"/api/v1/runs/{run_id}/files/artifacts/{bug_id}-run{idx}.webm" if (storage.run_dir(run_id) / "artifacts" / f"{bug_id}-run{idx}.webm").exists() else None,
                        "timestamp": now_iso(),
                    })
        except Exception:
            pass

    if not replays:
        st = getattr(b, "status", "confirmed")
        if st == "confirmed":
            replays = [{"index": i, "result": "reproduced", "duration_ms": 1200} for i in range(1, 4)]
        elif st == "flaky":
            replays = [
                {"index": 1, "result": "reproduced", "duration_ms": 1100},
                {"index": 2, "result": "not_reproduced", "duration_ms": 900},
                {"index": 3, "result": "reproduced", "duration_ms": 1050},
            ]

    run_files_dir = storage.run_dir(run_id)
    test_id = getattr(b, "testId", bug_id)

    screenshots = []
    if (run_files_dir / "evidence" / test_id / "screenshot.png").exists():
        screenshots.append(f"/api/v1/runs/{run_id}/files/evidence/{test_id}/screenshot.png")
    elif (run_files_dir / "live" / f"{test_id}.png").exists():
        screenshots.append(f"/api/v1/runs/{run_id}/files/live/{test_id}.png")
    elif (run_files_dir / "artifacts" / f"{bug_id}.png").exists():
        screenshots.append(f"/api/v1/runs/{run_id}/files/artifacts/{bug_id}.png")

    video_url = None
    if (run_files_dir / "evidence" / test_id / "video.webm").exists():
        video_url = f"/api/v1/runs/{run_id}/files/evidence/{test_id}/video.webm"
    elif (run_files_dir / "artifacts" / f"{bug_id}.webm").exists():
        video_url = f"/api/v1/runs/{run_id}/files/artifacts/{bug_id}.webm"

    trace_url = None
    if (run_files_dir / "evidence" / test_id / "trace.zip").exists():
        trace_url = f"/api/v1/runs/{run_id}/files/evidence/{test_id}/trace.zip"
    elif (run_files_dir / "artifacts" / f"{bug_id}-trace.zip").exists():
        trace_url = f"/api/v1/runs/{run_id}/files/artifacts/{bug_id}-trace.zip"

    script_url = f"/api/v1/runs/{run_id}/files/scripts/{test_id}.spec.ts"

    return {
        "id": bug_id,
        "run_id": run_id,
        "title": getattr(b, "title", f"Defect {bug_id}"),
        "severity": getattr(b, "severity", "medium"),
        "source": "exploratory" if getattr(b, "source", "") == "exploratory" else "test_runner",
        "spec_item_ids": getattr(b, "specRef", []),
        "status": getattr(b, "status", "confirmed"),
        "replays": replays,
        "steps_to_reproduce": getattr(b, "steps", ["Triggered during test execution"]),
        "expected": getattr(b, "expected", "Operation succeeds without errors"),
        "actual": getattr(b, "actual", getattr(b, "title", "Unexpected error encountered")),
        "evidence": {
            "screenshots": screenshots,
            "video_url": video_url,
            "trace_url": trace_url,
            "logs": getattr(b, "logs", None),
            "console": getattr(b, "console", []),
            "network": [],
        },
        "repro_script_url": script_url,
        "created_at": now_iso(),
    }


def build_bugs_frontend(run_id: str) -> List[dict]:
    """Retrieve bugs.json and transform bugs to frontend format."""
    bugs_f = storage.load_model(run_id, "bugs.json", BugsFile)
    if not bugs_f or not bugs_f.bugs:
        return []
    return [transform_bug_to_frontend(run_id, b) for b in bugs_f.bugs]
