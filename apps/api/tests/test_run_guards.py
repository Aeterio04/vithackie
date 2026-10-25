"""Regression tests for the run-state bugs seen on the imocha run (0 specs 'finished successfully', duplicate execution)."""

import threading
import time
from pathlib import Path

import pytest

from kawach.core.config import settings
from kawach.schemas import Budgets, Catalog, Run, RunInput, TestCase
from kawach.services import run_service
from kawach.services.spec_driven import build_spec_driven_catalog, selected_test_ids
from kawach.services.spec_structured import parse_structured_spec
from kawach.storage import artifacts as storage
from kawach.workflows import execute as wf

SPEC = Path(__file__).resolve().parents[3] / "QA_inputs" / "IMOCHA_SPEC.md"


@pytest.fixture
def run(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(settings, "runs_dir", runs)

    def make(stage: str, tests=None, run_id="r1"):
        ts = "2026-10-25T00:00:00Z"
        storage.save_model(run_id, "input.json", RunInput(runId=run_id, createdAt=ts, targetUrl="https://x.test/", mode="manual", budgets=Budgets()))
        storage.save_model(run_id, "run.json", Run(runId=run_id, createdAt=ts, updatedAt=ts, stage=stage, mode="manual", targetUrl="https://x.test/"))
        if tests is not None:
            storage.save_model(run_id, "catalog.json", Catalog(runId=run_id, generatedAt=ts, tests=tests))
        return run_id

    return make


def _tc(i, status="approved", script=None, script_status="pending"):
    return TestCase(id=f"T{i:02d}", title="t", description="d", status=status, script=script, scriptStatus=script_status)


@pytest.mark.parametrize("stage", ["created", "exploring", "planning"])
def test_start_during_exploration_is_a_noop(run, monkeypatch, stage):
    rid = run(stage)
    called = []
    monkeypatch.setattr(run_service, "run_execute", lambda r: called.append(r))
    out = run_service.resume_run(rid)
    assert out.stage == stage and not called  # previously: stage jumped to scripting and a 0-spec run 'finished'


def test_start_on_finished_run_needs_retry(run, monkeypatch):
    rid = run("done")
    monkeypatch.setattr(run_service, "run_execute", lambda r: None)
    assert run_service.resume_run(rid).stage == "done"
    assert run_service.resume_run(rid, retry=True).stage in ("scripting", "running", "done")


def test_terminal_stage_cannot_regress(run):
    rid = run("done")
    assert storage.set_stage(rid, "exploring").stage == "done"
    storage.reopen_run(rid)
    assert storage.set_stage(rid, "scripting").stage == "scripting"


def test_duplicate_execute_is_single_flight(run, monkeypatch):
    rid = run("scripting", tests=[_tc(1)])
    storage.write_json(rid, "gate_result.json", {"status": "passed"})
    started, release, count = threading.Event(), threading.Event(), []

    class G:
        def invoke(self, state):
            count.append(1)
            started.set()
            release.wait(5)

    monkeypatch.setattr(wf, "_graph2", G())
    t = threading.Thread(target=wf.run_execute, args=(rid,))
    t.start()
    assert started.wait(3)
    wf.run_execute(rid)  # second request while the first is running
    release.set()
    t.join(3)
    assert len(count) == 1


def test_zero_scripts_fails_loudly(run):
    rid = run("scripting", tests=[_tc(1), _tc(2)])
    assert wf._verify_scripts_or_fail(rid) is False
    r = storage.get_run(rid)
    assert r.stage == "script_generation_failed" and "T01" in (r.error or "")


def test_no_approved_tests_fails(run):
    rid = run("scripting", tests=[_tc(1, status="rejected")])
    assert wf._verify_scripts_or_fail(rid) is False
    assert storage.get_run(rid).stage == "script_generation_failed"


def test_scripts_ok_passes(run):
    rid = run("scripting", tests=[_tc(1, script="scripts/T01.spec.ts", script_status="ok")])
    assert wf._verify_scripts_or_fail(rid) is True


def test_priority_tiers_on_imocha_spec():
    spec = parse_structured_spec(SPEC.read_text(encoding="utf-8"))
    cat = build_spec_driven_catalog("r", spec)
    for t in cat.tests:
        t.status = "approved"
    assert len(selected_test_ids(cat, "P0")) == 12
    assert len(selected_test_ids(cat, "P0+P1")) > 12
    assert len(selected_test_ids(cat, "all")) == 46
    smoke = selected_test_ids(cat, "smoke")
    assert 0 < len(smoke) < 12 and set(smoke) <= set(selected_test_ids(cat, "P0"))
    with pytest.raises(ValueError):
        selected_test_ids(cat, "P9")


def test_budget_suggestion_never_below_spec_needs():
    from kawach.services.spec_budgets import estimate, suggest_budgets, test_timeout_ms

    raw = SPEC.read_text(encoding="utf-8")
    est = estimate(raw, "P0")
    b = suggest_budgets(raw, Budgets())
    assert b.maxPages >= est["pagesNeeded"] and b.maxTests == 46
    assert test_timeout_ms("TC-LOAD-001") == 60000 and test_timeout_ms("TC-LINK-001") > 60000
