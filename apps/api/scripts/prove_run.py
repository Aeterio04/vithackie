"""Drive the REAL create_run -> explore -> plan -> review gate -> execute pipeline end to end and print per-stage timings.

Reproduces the UI behaviour that broke the imocha run: /start is called right after creation and the review is
submitted twice. Usage: python scripts/prove_run.py <tier: P0|P0+P1|all|smoke>
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kawach.schemas import ReviewDecision  # noqa: E402
from kawach.services.catalog_service import batch_review  # noqa: E402
from kawach.services.run_service import create_run, resume_run  # noqa: E402
from kawach.storage import artifacts as storage  # noqa: E402

SPEC = Path(__file__).resolve().parents[3] / "QA_inputs" / "IMOCHA_SPEC.md"
tier = sys.argv[1] if len(sys.argv) > 1 else "P0"


def wait(run_id, stages, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = storage.get_run(run_id).stage
        if st in stages:
            return st
        time.sleep(1)
    raise TimeoutError(f"timeout waiting for {stages}; stage={storage.get_run(run_id).stage}")


def secs(a, b):
    f = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    return round((f(b) - f(a)).total_seconds(), 1)


t_start = time.time()
run = create_run("https://www.imocha.io/", mode="manual", prompt="iMocha website (read-only)", spec_raw=SPEC.read_text(encoding="utf-8"))
rid = run.runId
print("RUN", rid)
# What the UI does right after creating the run:
after = resume_run(rid)
print("start-after-create ->", after.stage, "(must stay a pre-review stage)")

wait(rid, {"awaiting_review", "failed", "done_with_environment_issue"}, 600)
t_gate_to_review = time.time() - t_start
print("reached", storage.get_run(rid).stage, f"after {t_gate_to_review:.1f}s")

cat = storage.load_model(rid, "catalog.json", storage.Catalog)
batch_review(rid, [ReviewDecision(testId=t.id, decision="approved", reason="proof run") for t in cat.tests])
t_review = time.time()
resume_run(rid, tier=tier)
resume_run(rid, tier=tier)  # double submit (client retry / double click)
final = wait(rid, set(storage.TERMINAL_STAGES), 3600)
t_end = time.time()

run = storage.get_run(rid)
res = storage.read_json(rid, "results.json") or {}
summ = res.get("summary", {})
print("\nFINAL STAGE:", final, "| error:", run.error)
print("TOTAL wall:", round(t_end - t_start, 1), "s | execution (approve->terminal):", round(t_end - t_review, 1), "s")
print("STAGE TIMINGS (from run.json stageTimes):")
for name, st in run.stageTimes.items():
    if st.endedAt:
        print(f"  {name:28s} {secs(st.startedAt, st.endedAt):8.1f}s")
print("RESULTS SUMMARY:", json.dumps(summ))
sel = [t for t in res.get("tests", []) if t["outcome"] != "not_run"]
print("executed specs:", len(sel), "| not_run (outside tier):", len([t for t in res.get("tests", []) if t["outcome"] == "not_run"]))
log = storage.get_run_logs(rid) if hasattr(storage, "get_run_logs") else []
for e in storage.run_dir(rid).joinpath("pipeline.log").read_text(encoding="utf-8").splitlines():
    if any(k in e for k in ("Circuit", "ignored", "Dispatching", "finished", "gate", "FAILED", "Explorer", "scripts generated", "WARN", "ERROR")):
        print("  LOG", e[:200])
