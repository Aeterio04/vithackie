"""Unit and integration tests for FastAPI backend application (Prompt C4)."""

import io
import json
import os
from pathlib import Path
import shutil
import time
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.models import (
    Budgets,
    Catalog,
    Results,
    Run,
    RunInput,
    StageTime,
    TestCase,
    TestResult,
)
from app import graphs
from app.agents import planner
from app import storage
from app.main import app

TestCase.__test__ = False
TestResult.__test__ = False


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    """Fixture that configures settings for a clean temporary test environment."""
    test_runs_dir = tmp_path / "runs"
    test_runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", test_runs_dir)
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"])
    monkeypatch.setattr(settings, "STUB_MODE", 1)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")

    # Fast sleep in stub pipeline to make tests snappy
    real_sleep = time.sleep
    import app.main as app_main
    monkeypatch.setattr(app_main.time, "sleep", lambda s: real_sleep(min(s, 0.01)))

    with TestClient(app) as client:
        yield {
            "client": client,
            "runs_dir": test_runs_dir,
            "tmp_path": tmp_path,
        }


def test_health_and_config(api_env):
    """Test GET /health and GET /config endpoints with dual mount paths."""
    client = api_env["client"]

    # Health endpoints
    res1 = client.get("/health")
    assert res1.status_code == 200
    assert res1.json() == {"ok": True}

    res2 = client.get("/api/v1/health")
    assert res2.status_code == 200
    assert res2.json()["ok"] is True

    # Config endpoints
    cfg1 = client.get("/config")
    assert cfg1.status_code == 200
    data1 = cfg1.json()
    assert "allowedHosts" in data1
    assert "budgets" in data1
    assert data1["defaultTargetUrl"] == "http://localhost:4000"
    assert data1["stubMode"] is True

    cfg2 = client.get("/api/v1/config/defaults")
    assert cfg2.status_code == 200
    assert cfg2.json()["allowedHosts"] == data1["allowedHosts"]


def test_validation_errors_reported_together(api_env):
    """Bad URL host, empty spec, and bad spec line are returned together in errors (422)."""
    client = api_env["client"]

    # Both bad host and bad spec line
    payload = {
        "targetUrl": "http://unauthorized-domain.com",
        "spec": "Line 1 not starting with S\nS2: valid item",
        "mode": "manual",
    }
    res = client.post("/runs", json=payload)
    assert res.status_code == 422
    body = res.json()
    assert "errors" in body
    fields = [err["field"] for err in body["errors"]]
    messages = [err["message"] for err in body["errors"]]

    assert "targetUrl" in fields
    assert any("Host not allowed" in m for m in messages)
    assert "spec" in fields
    assert any("Line 1 must start with S<number>:" in m for m in messages)

    # Empty spec error
    empty_spec_payload = {
        "targetUrl": "http://localhost:4000",
        "spec": "",
        "mode": "manual",
    }
    res2 = client.post("/runs", json=empty_spec_payload)
    assert res2.status_code == 422
    err_msgs = [e["message"] for e in res2.json()["errors"]]
    assert any("Spec must contain at least one item like 'S1: ...'" in m for m in err_msgs)


def test_manual_run_happy_path(api_env):
    """Happy path manual flow: POST /runs -> poll awaiting_review -> PUT catalog -> POST tests -> POST execute -> done."""
    client = api_env["client"]
    password_secret = "TopSecretPassword123!"

    payload = {
        "targetUrl": "http://localhost:4000",
        "prompt": "Test user signup and authentication",
        "spec": "S1: Users can sign up\n  with a valid email and password\nS2: Sign in with valid credentials",
        "username": "tester@example.com",
        "password": password_secret,
        "mode": "manual",
    }

    # 1. Start run
    res = client.post("/runs", json=payload)
    assert res.status_code == 201
    run_id = res.json()["runId"]
    assert len(run_id) >= 15

    # Verify secrets.json exists and password is NOT in input.json
    run_dir = api_env["runs_dir"] / run_id
    assert (run_dir / "secrets.json").exists()
    input_data = json.loads((run_dir / "input.json").read_text(encoding="utf-8"))
    assert "password" not in input_data

    # 2. Poll until stage awaiting_review
    start_time = time.time()
    while time.time() - start_time < 30:
        view_res = client.get(f"/runs/{run_id}")
        assert view_res.status_code == 200
        view = view_res.json()
        if view["run"]["stage"] == "awaiting_review":
            break
        time.sleep(0.05)
    assert view["run"]["stage"] == "awaiting_review"
    assert view["catalog"] is not None
    assert len(view["catalog"]["tests"]) > 0

    # 3. PUT /runs/{id}/catalog - Reject one test and verify duplicate ID validation
    cat_tests = view["catalog"]["tests"]

    # Duplicate test ID should fail with 422
    dup_payload = {"tests": [cat_tests[0], cat_tests[0]]}
    dup_res = client.put(f"/runs/{run_id}/catalog", json=dup_payload)
    assert dup_res.status_code == 422
    assert "Duplicate test ID" in dup_res.json()["detail"]

    # Reject the first test
    cat_tests[0]["status"] = "rejected"
    put_res = client.put(f"/runs/{run_id}/catalog", json={"tests": cat_tests})
    assert put_res.status_code == 200
    updated_catalog = put_res.json()
    assert updated_catalog["tests"][0]["status"] == "rejected"

    # 4. POST /runs/{id}/tests - Plan a single test from human prompt
    add_res = client.post(f"/runs/{run_id}/tests", json={"prompt": "Test password reset link expiration"})
    assert add_res.status_code == 200
    new_test = add_res.json()
    assert new_test["id"].startswith("T")
    assert "password reset" in new_test["title"].lower()

    # 5. POST /runs/{id}/execute - Approve remaining proposed tests and proceed to scripting
    exec_res = client.post(f"/runs/{run_id}/execute")
    assert exec_res.status_code == 202
    assert exec_res.json()["stage"] == "scripting"

    # 6. Poll until stage done
    start_time = time.time()
    while time.time() - start_time < 30:
        view_res = client.get(f"/runs/{run_id}")
        assert view_res.status_code == 200
        view = view_res.json()
        if view["run"]["stage"] == "done":
            break
        time.sleep(0.05)

    assert view["run"]["stage"] == "done"

    # Check bugs include confirmed, flaky, and not_reproduced
    bug_statuses = {b["status"] for b in view["bugs"]}
    assert "confirmed" in bug_statuses
    assert "flaky" in bug_statuses
    assert "not_reproduced" in bug_statuses
    assert view["hasReport"] is True

    # Critical Security Assertion: Password NEVER leaked in GET /runs/{id}
    assert password_secret not in view_res.text

    # 7. GET /runs/{id}/report -> 200 markdown
    report_res = client.get(f"/runs/{run_id}/report")
    assert report_res.status_code == 200
    assert "# QA Report:" in report_res.text
    assert password_secret not in report_res.text

    # 8. GET /runs/{id}/export -> returns a valid zip
    export_res = client.get(f"/runs/{run_id}/export")
    assert export_res.status_code == 200
    assert "attachment" in export_res.headers.get("content-disposition", "")
    assert f"{run_id}-passing-tests.zip" in export_res.headers.get("content-disposition", "")

    # Inspect zip contents in memory
    zf = zipfile.ZipFile(io.BytesIO(export_res.content))
    namelist = zf.namelist()
    assert "fixtures.ts" in namelist
    assert "playwright.config.ts" in namelist
    assert "package.json" in namelist
    assert "README.md" in namelist

    # Verify rewritten imports in passing scripts
    script_files = [name for name in namelist if name.startswith("scripts/") and name.endswith(".spec.ts")]
    assert len(script_files) > 0
    for sfile in script_files:
        script_code = zf.read(sfile).decode("utf-8")
        assert "../../../runner/fixtures" not in script_code
        assert "../../../apps/runner/fixtures" not in script_code
        assert "./fixtures" in script_code

    # Verify exported test project resolves ./fixtures from script location
    assert "fixtures.ts" in namelist
    assert "scripts/fixtures.ts" in namelist
    for sfile in script_files:
        spec_parent = Path(sfile).parent
        resolved_fixture = (spec_parent / "fixtures.ts").as_posix()
        assert resolved_fixture in namelist

    # Verify password is NOT in export zip
    for name in namelist:
        file_bytes = zf.read(name)
        assert password_secret.encode("utf-8") not in file_bytes


def test_autonomous_run_reaches_done(api_env):
    """Autonomous run reaches done automatically without requiring manual review or execution calls."""
    client = api_env["client"]

    payload = {
        "targetUrl": "http://localhost:4000",
        "prompt": "Autonomous regression suite",
        "spec": "S1: Verify home page loads\nS2: Check search bar",
        "mode": "autonomous",
    }
    res = client.post("/runs", json=payload)
    assert res.status_code == 201
    run_id = res.json()["runId"]

    # Poll until done
    start_time = time.time()
    while time.time() - start_time < 30:
        view_res = client.get(f"/runs/{run_id}")
        assert view_res.status_code == 200
        view = view_res.json()
        if view["run"]["stage"] == "done":
            break
        time.sleep(0.05)

    assert view["run"]["stage"] == "done"
    assert view["reviewLog"] is not None


def test_concurrency_conflict(api_env):
    """Starting a run while another run is in an active stage returns 409 Conflict."""
    client = api_env["client"]

    # Create an active run directly on disk
    active_run_id = storage.new_run_id()
    now = "2026-10-18T00:00:00Z"
    active_run = Run(
        runId=active_run_id,
        createdAt=now,
        updatedAt=now,
        stage="exploring",
        mode="manual",
        targetUrl="http://localhost:4000",
        stageTimes={"exploring": StageTime(startedAt=now, endedAt=None)},
        golden=False,
    )
    storage.save_model(active_run_id, "run.json", active_run)

    # Attempt to start a second run
    payload = {
        "targetUrl": "http://localhost:4000",
        "spec": "S1: New run spec",
        "mode": "manual",
    }
    res = client.post("/runs", json=payload)
    assert res.status_code == 409
    assert "Another run is in progress" in res.json()["detail"]


def test_stage_transition_guards(api_env):
    """Calling PUT /catalog or POST /execute at wrong stage returns 409."""
    client = api_env["client"]

    # Create a run in 'exploring' stage
    run_id = storage.new_run_id()
    now = "2026-10-18T00:00:00Z"
    run = Run(
        runId=run_id,
        createdAt=now,
        updatedAt=now,
        stage="exploring",
        mode="manual",
        targetUrl="http://localhost:4000",
        stageTimes={"exploring": StageTime(startedAt=now, endedAt=None)},
        golden=False,
    )
    storage.save_model(run_id, "run.json", run)

    # PUT /catalog when stage is not awaiting_review -> 409
    put_res = client.put(f"/runs/{run_id}/catalog", json={"tests": []})
    assert put_res.status_code == 409

    # POST /execute when stage is not awaiting_review -> 409
    exec_res = client.post(f"/runs/{run_id}/execute")
    assert exec_res.status_code == 409

    # POST /tests when stage is not awaiting_review -> 409
    test_res = client.post(f"/runs/{run_id}/tests", json={"prompt": "Some test"})
    assert test_res.status_code == 409


def test_add_test_error_mappings(api_env, monkeypatch):
    """POST /runs/{id}/tests maps ValueError to 422 and LLM errors to 502."""
    client = api_env["client"]

    # Create run in awaiting_review stage
    run_id = storage.new_run_id()
    now = "2026-10-18T00:00:00Z"
    run = Run(
        runId=run_id,
        createdAt=now,
        updatedAt=now,
        stage="awaiting_review",
        mode="manual",
        targetUrl="http://localhost:4000",
        stageTimes={"awaiting_review": StageTime(startedAt=now, endedAt=None)},
        golden=False,
    )
    storage.save_model(run_id, "run.json", run)

    # 1. ValueError -> 422
    def mock_val_error(r_id, prompt):
        raise ValueError("Prompt is too ambiguous")

    monkeypatch.setattr(planner, "plan_single_test", mock_val_error)
    res_val = client.post(f"/runs/{run_id}/tests", json={"prompt": "Ambiguous"})
    assert res_val.status_code == 422
    assert "Prompt is too ambiguous" in res_val.json()["detail"]

    # 2. LLM / network error -> 502
    def mock_llm_error(r_id, prompt):
        raise RuntimeError("Claude API quota exceeded")

    monkeypatch.setattr(planner, "plan_single_test", mock_llm_error)
    res_llm = client.post(f"/runs/{run_id}/tests", json={"prompt": "Valid test"})
    assert res_llm.status_code == 502
    assert "Claude API quota exceeded" in res_llm.json()["detail"]


def test_path_traversal_and_secrets_security(api_env):
    """Path traversal, symlink escapes, and secrets.json/input.json access are blocked with 403 or 404."""
    client = api_env["client"]

    run_id = storage.new_run_id()
    run_dir = api_env["runs_dir"] / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy files
    (run_dir / "secrets.json").write_text('{"password": "secret"}', encoding="utf-8")
    (run_dir / "input.json").write_text('{"username": "test"}', encoding="utf-8")
    (run_dir / "safe.txt").write_text("Hello safe world", encoding="utf-8")

    # 1. Traversal outside run directory -> 403
    res_trav = client.get(f"/runs/{run_id}/files/../../.env")
    assert res_trav.status_code in (403, 404)

    # 2. Direct secrets.json access -> 403
    res_sec = client.get(f"/runs/{run_id}/files/secrets.json")
    assert res_sec.status_code == 403

    # 3. Direct input.json access -> 403
    res_inp = client.get(f"/runs/{run_id}/files/input.json")
    assert res_inp.status_code == 403

    # 4. Symlink pointing outside run directory -> 403
    outside_file = api_env["tmp_path"] / "outside.txt"
    outside_file.write_text("secret outside", encoding="utf-8")
    symlink_path = run_dir / "symlink_escape"
    try:
        os.symlink(outside_file, symlink_path)
        res_sym = client.get(f"/runs/{run_id}/files/symlink_escape")
        assert res_sym.status_code in (403, 404)
    except OSError:
        # On Windows without SeCreateSymbolicLinkPrivilege, symlinks might require admin
        pass

    # 5. Legitimate file access -> 200
    res_safe = client.get(f"/runs/{run_id}/files/safe.txt")
    assert res_safe.status_code == 200
    assert res_safe.text == "Hello safe world"


def test_background_failure_records_error(api_env, monkeypatch):
    """A run whose background function raises ends 'failed' with the error message."""
    client = api_env["client"]

    def crash_pipeline(run_id):
        raise RuntimeError("Simulated pipeline failure in agent")

    monkeypatch.setattr(graphs, "run_pipeline", crash_pipeline)

    payload = {
        "targetUrl": "http://localhost:4000",
        "spec": "S1: Crash test spec",
        "mode": "manual",
    }
    res = client.post("/runs", json=payload)
    assert res.status_code == 201
    run_id = res.json()["runId"]

    # Poll until stage failed
    start_time = time.time()
    while time.time() - start_time < 10:
        view_res = client.get(f"/runs/{run_id}")
        assert view_res.status_code == 200
        view = view_res.json()
        if view["run"]["stage"] == "failed":
            break
        time.sleep(0.05)

    assert view["run"]["stage"] == "failed"
    assert "Simulated pipeline failure in agent" in view["run"]["error"]


def test_startup_recovery(tmp_path, monkeypatch):
    """Server restart marks stale active runs as failed with 'Server restarted while the run was in progress'."""
    test_runs_dir = tmp_path / "runs"
    test_runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", test_runs_dir)

    # Seed an abandoned run in 'scripting' stage
    stale_id = "run_20261018_120000_stale"
    sdir = test_runs_dir / stale_id
    sdir.mkdir(parents=True, exist_ok=True)
    now = "2026-10-18T12:00:00Z"

    stale_run = Run(
        runId=stale_id,
        createdAt=now,
        updatedAt=now,
        stage="scripting",
        mode="manual",
        targetUrl="http://localhost:4000",
        stageTimes={"scripting": StageTime(startedAt=now, endedAt=None)},
        golden=False,
    )
    with open(sdir / "run.json", "w", encoding="utf-8") as f:
        json.dump(stale_run.model_dump(by_alias=True, mode="json"), f, indent=2)

    # Start TestClient to trigger app lifespan
    with TestClient(app) as client:
        res = client.get(f"/runs/{stale_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["run"]["stage"] == "failed"
        assert "Server restarted while the run was in progress" in data["run"]["error"]
