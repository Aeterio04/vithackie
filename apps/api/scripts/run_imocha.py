"""CLI driver for the spec-driven iMocha pipeline (no DB / HTTP server needed).

  python scripts/run_imocha.py prepare                # run dir + catalog + alignment + scripts + load check
  python scripts/run_imocha.py run <run_id> <mode> [TC-ID ...]
Writes under <runs_dir>/<run_id>/ : spec_structured.json, catalog.json, alignment.json,
scripts/*.spec.ts, spec_results_<mode>.json, evidence/<mode>/<TC>/...
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kawach.core.clock import now_iso  # noqa: E402
from kawach.core.config import settings  # noqa: E402
from kawach.core.ids import new_run_id  # noqa: E402
from kawach.schemas import Budgets, Catalog, Run, RunInput  # noqa: E402
from kawach.storage import artifacts as storage  # noqa: E402

SPEC = Path(__file__).resolve().parents[3] / "QA_inputs" / "IMOCHA_SPEC.md"
TARGET = "https://www.imocha.io/"


def prepare() -> str:
    from kawach.agents.planner.agent import plan_catalog
    from kawach.execution.runner import normalize_path
    from kawach.services.run_service import compute_alignment
    from kawach.services.spec_parser import parse_spec_raw
    from kawach.services.spec_scripts import write_spec_scripts

    raw = SPEC.read_text(encoding="utf-8")
    run_id = new_run_id()
    ts = now_iso()
    run_input = RunInput(
        runId=run_id, createdAt=ts, targetUrl=TARGET, prompt="iMocha website (read-only, safe mode)",
        specRaw=raw, spec=parse_spec_raw(raw), mode="manual",
        budgets=Budgets(maxPages=40, exploreSeconds=90, maxTests=100, testTimeoutMs=150000),
    )
    storage.save_model(run_id, "input.json", run_input)
    storage.save_model(run_id, "run.json", Run(runId=run_id, createdAt=ts, updatedAt=ts, stage="created", mode="manual", targetUrl=TARGET))
    catalog = plan_catalog(run_id)
    report = compute_alignment(run_id)
    print("alignment:", json.dumps({k: v for k, v in report.items() if k not in ("specHash",)}, indent=1))
    assert report["canStartExecution"], report["blockReason"]
    # review gate (manual mode): reviewer approves the aligned catalog
    for t in catalog.tests:
        t.status = "approved"
    storage.save_model(run_id, "catalog.json", catalog)
    write_spec_scripts(run_id)

    runner = Path(settings.repo_root) / "apps" / "runner"
    env_dir = storage.run_dir(run_id) / "scripts"
    import os, shutil
    env = os.environ.copy()
    env.update(SPEC_DIR=normalize_path(env_dir), BASE_URL=TARGET, OUTPUT_DIR=normalize_path(env_dir.parent / "raw" / "list"), JSON_REPORT=normalize_path(env_dir.parent / "raw" / "list.json"))
    npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    p = subprocess.run([npx, "playwright", "test", "--list", "--config", "playwright.config.ts"], cwd=runner, env=env, capture_output=True, text=True, shell=os.name == "nt")
    tail = (p.stdout or "").strip().splitlines()[-3:]
    print("load check exit", p.returncode, tail, (p.stderr or "")[-800:])
    assert p.returncode == 0, "scripts failed to load"
    print("RUN_ID", run_id)
    return run_id


def run(run_id: str, mode: str, only):
    from kawach.execution.spec_runner import run_spec_tests, write_results_model

    storage.set_stage(run_id, "running", step=f"spec-driven {mode}")
    out = run_spec_tests(run_id, mode=mode, workers=2, only=only or None)
    if not only:
        write_results_model(run_id, out)
    print(json.dumps({"summary": out["summary"], "durationSeconds": out["durationSeconds"], "rate": out["rate"], "exit": out["exitCode"]}, indent=1))
    for e in out["results"]:
        print(f"{e['id']:14s} {e['status']:19s} {(e.get('errorMessage') or '')[:150]}")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prepare":
        prepare()
    elif cmd == "run":
        run(sys.argv[2], sys.argv[3], sys.argv[4:])
