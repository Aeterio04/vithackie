import json
import logging

import pytest

from kawach_mcp.errors import KawachError
from kawach_mcp.tools import runs
from conftest import API, PASSWORD

ALLOWED = {"allowed": True, "reachable": True, "status_code": 200, "reason": None}
RUN = {"runId": "run_1", "id": "run_1", "stage": "created", "review_mode": "manual",
       "targetUrl": "http://localhost:3000", "created_at": "2026-01-01T00:00:00Z", "progress": 0}


@pytest.fixture
def check_ok(api):
    return api.post(API + "/targets/check").respond(200, json=ALLOWED)


@pytest.mark.parametrize("kwargs,msg", [
    ({}, "target_url or project_id"),
    ({"target_url": "http://localhost:3000", "spec_id": "s1", "spec_file_path": "x.md"}, "only one of spec_id"),
    ({"target_url": "http://localhost:3000", "review_mode": "yolo"}, "Invalid review_mode"),
    ({"target_url": "http://localhost:3000", "username": "bob"}, "both username and password"),
    ({"target_url": "localhost:3000"}, "Invalid target_url"),
])
async def test_start_run_validation(guest, kwargs, msg):
    with pytest.raises(KawachError, match=msg):
        await runs.start_run(**kwargs)


async def test_start_run_budget_out_of_range(api, guest, defaults_route):
    with pytest.raises(KawachError, match="between 1 and 100"):
        await runs.start_run(target_url="http://localhost:3000", budgets={"max_pages": 500})


async def test_start_run_happy_path_body(api, guest, defaults_route, check_ok):
    route = api.post(API + "/runs").respond(201, json=RUN)
    r = await runs.start_run(target_url="http://localhost:3000", prompt="focus on login",
                             spec_text="S1: x", budgets={"max_pages": 5}, username="bob", password=PASSWORD)
    body = json.loads(route.calls[0].request.content)
    assert body == {"target_url": "http://localhost:3000", "review_mode": "manual", "prompt": "focus on login",
                    "spec_text": "S1: x", "budgets": {"max_pages": 5},
                    "credentials": {"username": "bob", "password": PASSWORD}}
    assert r["run_id"] == "run_1" and r["mode"] == "manual"
    assert "awaiting_review" in r["next_step_hint"] and "wait_for_run" in r["next_step_hint"]


async def test_start_run_password_never_leaks(api, guest, defaults_route, check_ok, caplog):
    caplog.set_level(logging.DEBUG)
    api.post(API + "/runs").respond(201, json=RUN)
    r = await runs.start_run(target_url="http://localhost:3000", username="bob", password=PASSWORD)
    assert PASSWORD not in str(r) and PASSWORD not in caplog.text
    api.post(API + "/runs").respond(500, text=f"boom {PASSWORD}")
    with pytest.raises(KawachError) as ei:
        await runs.start_run(target_url="http://localhost:3000", username="bob", password=PASSWORD)
    assert PASSWORD not in str(ei.value) and PASSWORD not in caplog.text


async def test_start_run_from_project_uses_url_and_mode(api, guest, check_ok):
    api.get(API + "/projects/p1").respond(200, json={"id": "p1", "targetUrl": "http://localhost:4000", "defaultMode": "autonomous"})
    route = api.post(API + "/runs").respond(201, json=dict(RUN, review_mode="autonomous"))
    r = await runs.start_run(project_id="p1")
    body = json.loads(route.calls[0].request.content)
    assert body["target_url"] == "http://localhost:4000" and body["review_mode"] == "autonomous"
    assert body["project_id"] == "p1" and "Autonomous" in r["next_step_hint"]


async def test_start_run_aborts_when_target_blocked(api, guest):
    api.post(API + "/targets/check").respond(200, json={"allowed": False, "reachable": True, "reason": "nope"})
    create = api.post(API + "/runs").respond(201, json=RUN)
    with pytest.raises(KawachError, match="Blocked by SSRF policy"):
        await runs.start_run(target_url="http://evil.example")
    assert create.call_count == 0


async def test_start_run_uploads_spec_file_first(api, guest, defaults_route, check_ok, tmp_path):
    f = tmp_path / "spec.md"
    f.write_text("S1: a")
    api.post(API + "/specs/upload").respond(200, json={"spec_id": "spec_1", "filename": "spec.md", "item_count": 1})
    route = api.post(API + "/runs").respond(201, json=RUN)
    await runs.start_run(target_url="http://localhost:3000", spec_file_path=str(f))
    assert json.loads(route.calls[0].request.content)["spec_id"] == "spec_1"


async def test_list_runs_filters_sorts_and_caps(api, guest):
    data = [dict(RUN, runId=f"r{i}", stage="done" if i % 2 else "failed", created_at=f"2026-01-0{i}") for i in range(1, 7)]
    route = api.get(API + "/runs").respond(200, json=data)
    r = await runs.list_runs(project_id="p1", stage="done", limit=2)
    assert route.calls[0].request.url.params["project_id"] == "p1"
    assert [x["run_id"] for x in r["runs"]] == ["r5", "r3"] and r["truncated"] and r["total"] == 3
    with pytest.raises(KawachError, match="Invalid stage"):
        await runs.list_runs(stage="napping")


async def test_get_run_has_meaning_and_step(api, guest):
    api.get(API + "/runs/run_1").respond(200, json=dict(RUN, stage="running", progress=70, counts={"total_tests": 4}))
    api.get(API + "/runs/run_1/execution").respond(200, json={"workers": [{"status": "running", "current_step": "Login test"}]})
    r = await runs.get_run("run_1")
    assert r["stage"] == "running" and "Playwright" in r["meaning"]
    assert r["progress"] == {"stage": "running", "percent": 70, "step": "Login test"}
    assert r["metrics"] == {"total_tests": 4}


async def test_get_run_survives_missing_execution(api, guest):
    api.get(API + "/runs/run_1").respond(200, json=dict(RUN, stage="awaiting_review"))
    api.get(API + "/runs/run_1/execution").respond(404, json={"detail": "x"})
    r = await runs.get_run("run_1")
    assert r["progress"]["step"] is None and "approve_all_and_resume" in r["next_step_hint"]


async def test_resume_requires_awaiting_review(api, guest):
    api.get(API + "/runs/run_1").respond(200, json=dict(RUN, stage="running"))
    post = api.post(API + "/runs/run_1/resume").respond(200, json=RUN)
    with pytest.raises(KawachError, match="not 'awaiting_review'"):
        await runs.resume_run("run_1")
    assert post.call_count == 0
    api.get(API + "/runs/run_1").respond(200, json=dict(RUN, stage="awaiting_review"))
    api.post(API + "/runs/run_1/resume").respond(200, json=dict(RUN, stage="scripting"))
    assert (await runs.resume_run("run_1"))["stage"] == "scripting"


async def test_retry_only_failed_or_cancelled(api, guest):
    api.get(API + "/runs/run_1").respond(200, json=dict(RUN, stage="done"))
    with pytest.raises(KawachError, match="failed or cancelled"):
        await runs.retry_run("run_1")
    api.get(API + "/runs/run_1").respond(200, json=dict(RUN, stage="failed"))
    post = api.post(API + "/runs/run_1/retry").respond(200, json=dict(RUN, stage="scripting"))
    assert (await runs.retry_run("run_1"))["stage"] == "scripting" and post.call_count == 1


async def test_destructive_run_tools_need_confirm(api, guest):
    cancel = api.post(API + "/runs/run_1/cancel").respond(200, json=dict(RUN, stage="cancelled"))
    delete = api.delete(API + "/runs/run_1").respond(200, json={"ok": True})
    for r in (await runs.cancel_run("run_1"), await runs.delete_run("run_1"),
              await runs.cancel_run("run_1", confirm="yes"), await runs.delete_run("run_1", confirm=False)):
        assert r["done"] is False and "confirm" in r["message"]
    assert cancel.call_count == 0 and delete.call_count == 0
    assert (await runs.cancel_run("run_1", confirm=True))["stage"] == "cancelled"
    assert "deleted" in (await runs.delete_run("run_1", confirm=True))["message"]
