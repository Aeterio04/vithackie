"""Live smoke test against a running KAWACH backend, using the configured environment.

    .venv/Scripts/python scripts/smoke.py
"""

import asyncio
import sys

from kawach_mcp.client import get_client
from kawach_mcp.config import get_settings
from kawach_mcp.tools import bugs, catalog, observe, projects, reports, runs, system


async def main() -> int:
    print("settings:", get_settings().describe())
    calls = [
        ("health_check", system.health_check),
        ("get_defaults", system.get_defaults),
        ("whoami", system.whoami),
        ("list_projects", projects.list_projects),
        ("list_runs", runs.list_runs),
        ("get_stats", system.get_stats),
    ]
    failed = 0
    for name, fn in calls:
        try:
            res = await fn()
            if name == "health_check" and res.get("status") == "unreachable":
                raise RuntimeError(res["message"])
            if name == "whoami" and not res.get("authenticated"):
                raise RuntimeError(f"not authenticated ({res.get('note')})")
            print(f"PASS {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    total = len(calls)
    f2, t2 = await run_pass()
    failed, total = failed + f2, total + t2
    await get_client().aclose()
    print(f"{total - failed}/{total} passed")
    return 1 if failed else 0


async def run_pass() -> tuple[int, int]:
    """Read-only pass over the newest run: list_runs -> get_run -> get_catalog -> list_bugs -> ..."""
    try:
        rows = (await runs.list_runs(limit=1))["runs"]
    except Exception as e:
        print(f"FAIL run pass: list_runs: {e}")
        return 1, 1
    if not rows:
        print("SKIP run pass: no runs exist in this backend/account yet")
        return 0, 0
    rid = rows[0]["run_id"]
    print(f"newest run: {rid} (stage {rows[0]['stage']})")
    steps = [("get_run", lambda: runs.get_run(rid)), ("get_catalog", lambda: catalog.get_catalog(rid)),
             ("list_bugs", lambda: bugs.list_bugs(rid)), ("get_metrics", lambda: reports.get_metrics(rid)),
             ("get_report", lambda: reports.get_report(rid)), ("get_app_map", lambda: observe.get_app_map(rid))]
    if rows[0]["stage"] not in ("done", "failed", "cancelled", "awaiting_review"):
        steps.append(("tail_run_stream", lambda: observe.tail_run_stream(rid, seconds=5)))
    failed = 0
    for name, fn in steps:
        try:
            await fn()
            print(f"PASS {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    return failed, len(steps)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
