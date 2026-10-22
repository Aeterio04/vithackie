"""Unit tests for LangGraph workflows, orchestration, and STUB_MODE."""

import json
from unittest.mock import MagicMock
import pytest

from app.config import settings
from app.graphs import run_execute, run_explore_plan, run_pipeline
from app.models import Budgets, Catalog, Run, RunInput
from app import storage


@pytest.fixture
def run_fixture(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)
    monkeypatch.setattr(settings, "STUB_MODE", 1)

    def _create_run(run_id: str, mode: str = "manual"):
        run_input = RunInput(
            runId=run_id,
            createdAt="2026-10-18T00:00:00Z",
            targetUrl="http://localhost:4000",
            prompt="Testing LangGraph pipeline in STUB_MODE",
            specRaw="S1: Test 1\nS2: Test 2",
            mode=mode,
            budgets=Budgets(maxPages=5, maxTests=5),
        )
        storage.save_model(run_id, "input.json", run_input)
        storage.write_json(run_id, "secrets.json", {"password": "test_password"})

        run_obj = Run(
            runId=run_id,
            createdAt="2026-10-18T00:00:00Z",
            updatedAt="2026-10-18T00:00:00Z",
            stage="created",
            mode=mode,
            targetUrl="http://localhost:4000",
        )
        storage.save_model(run_id, "run.json", run_obj)
        return run_id

    return _create_run


def test_manual_mode_stops_at_awaiting_review(run_fixture):
    create_run = run_fixture
    run_id = create_run("test-manual-run", mode="manual")

    run_pipeline(run_id)

    run = storage.get_run(run_id)
    assert run.stage == "awaiting_review"
    assert (storage.run_dir(run_id) / "app_map.json").exists()
    assert (storage.run_dir(run_id) / "catalog.json").exists()
    # Graph 2 has not run yet
    assert not (storage.run_dir(run_id) / "results.json").exists()


def test_run_execute_completes_to_done(run_fixture):
    create_run = run_fixture
    run_id = create_run("test-execute-run", mode="manual")

    # Run explore and plan
    run_explore_plan(run_id)

    # Approve all tests in catalog
    cat = storage.load_model(run_id, "catalog.json", Catalog)
    assert cat is not None
    for t in cat.tests:
        t.status = "approved"
    storage.save_model(run_id, "catalog.json", cat)

    # Now execute Graph 2
    run_execute(run_id)

    run = storage.get_run(run_id)
    assert run.stage == "done"
    assert (storage.run_dir(run_id) / "results.json").exists()
    assert (storage.run_dir(run_id) / "bugs.json").exists()
    assert (storage.run_dir(run_id) / "metrics.json").exists()
    assert (storage.run_dir(run_id) / "report.md").exists()

    # Verify bug statuses (confirmed, flaky, not_reproduced)
    bugs_data = storage.read_json(run_id, "bugs.json")
    statuses = {b["status"] for b in bugs_data.get("bugs", [])}
    assert "confirmed" in statuses


def test_autonomous_mode_pipeline_runs_end_to_end(run_fixture):
    create_run = run_fixture
    run_id = create_run("test-auto-run", mode="autonomous")

    run_pipeline(run_id)

    run = storage.get_run(run_id)
    assert run.stage == "done"
    assert (storage.run_dir(run_id) / "review_log.json").exists()
    assert (storage.run_dir(run_id) / "report.md").exists()


def test_failure_in_node_fails_run_gracefully(run_fixture, monkeypatch):
    create_run = run_fixture
    run_id = create_run("test-fail-run", mode="autonomous")

    from app.graphs import stubs
    # Monkeypatch stub_explore to simulate failure
    monkeypatch.setattr(stubs, "stub_explore", MagicMock(side_effect=RuntimeError("Crawler crash test")))

    run_pipeline(run_id)

    run = storage.get_run(run_id)
    assert run.stage == "failed"
    assert "explore failed: Crawler crash test" in str(run.error)
    assert (storage.run_dir(run_id) / "error.log").exists()

    # Graph 2 must not have started
    assert not (storage.run_dir(run_id) / "results.json").exists()


def test_stage_sequence_order(run_fixture, monkeypatch):
    create_run = run_fixture
    run_id = create_run("test-sequence-run", mode="autonomous")

    recorded_stages = []
    orig_set_stage = storage.set_stage

    def mock_set_stage(r_id, stage, *args, **kwargs):
        if r_id == run_id and (not recorded_stages or recorded_stages[-1] != stage):
            recorded_stages.append(stage)
        return orig_set_stage(r_id, stage, *args, **kwargs)

    monkeypatch.setattr(storage, "set_stage", mock_set_stage)

    run_pipeline(run_id)

    # Check stage order sequence matching CONTRACTS section 3:
    # created -> exploring -> planning -> scripting -> running -> verifying -> reporting -> done
    expected_order = [
        "exploring",
        "planning",
        "scripting",
        "running",
        "verifying",
        "reporting",
        "done",
    ]
    assert recorded_stages == expected_order
