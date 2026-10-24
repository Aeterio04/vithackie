import json
import logging

import pytest

from kawach_mcp.errors import KawachError
from kawach_mcp.tools import projects
from conftest import API, PASSWORD

PROJECT = {"id": "p1", "name": "Shop", "targetUrl": "http://localhost:3000", "defaultMode": "manual",
           "budgets": {}, "savedTestCount": 2, "hasPat": False}


async def test_list_projects_compact_and_truncated(api, guest):
    rows = [dict(PROJECT, id=f"p{i}") for i in range(5)]
    api.get(API + "/projects").respond(200, json=rows)
    r = await projects.list_projects(limit=3)
    assert r["count"] == 3 and r["truncated"] is True and r["total"] == 5
    assert r["projects"][0]["target_url"] == "http://localhost:3000"
    assert r["projects"][0]["saved_test_count"] == 2


async def test_create_project_blocks_ssrf(api, guest, defaults_route):
    api.post(API + "/targets/check").respond(200, json={"allowed": False, "reachable": True, "reason": "Host not allowed"})
    create = api.post(API + "/projects").respond(201, json=PROJECT)
    with pytest.raises(KawachError, match="Blocked by SSRF policy"):
        await projects.create_project("Evil", "http://169.254.169.254/")
    assert create.call_count == 0


async def test_create_project_unreachable_still_creates(api, guest, defaults_route):
    api.post(API + "/targets/check").respond(200, json={"allowed": True, "reachable": False, "reason": "down"})
    create = api.post(API + "/projects").respond(201, json=PROJECT)
    r = await projects.create_project("Shop", "http://localhost:3000", default_mode="autonomous")
    assert r["target_check"]["verdict"].startswith("Unreachable")
    assert r["project"]["id"] == "p1"
    body = json.loads(create.calls[0].request.content)
    assert body == {"name": "Shop", "targetUrl": "http://localhost:3000", "defaultMode": "autonomous"}


@pytest.mark.parametrize("kwargs,msg", [
    ({"default_mode": "robotic"}, "Invalid default_mode"),
    ({"budgets": {"max_pages": 1000}}, "between 1 and 100"),
    ({"budgets": {"max_pages": "ten"}}, "whole number"),
    ({"budgets": {"bogus": 3}}, "Unknown budget key"),
    ({"budgets": {"parallel_workers": 0}}, "between 1 and 4"),
])
async def test_create_project_validation(api, guest, defaults_route, kwargs, msg):
    with pytest.raises(KawachError, match=msg):
        await projects.create_project("Shop", "http://localhost:3000", **kwargs)


async def test_update_project_rejects_empty(guest):
    with pytest.raises(KawachError, match="Nothing to update"):
        await projects.update_project("p1")


async def test_update_project_partial_body(api, guest):
    route = api.put(API + "/projects/p1").respond(200, json=dict(PROJECT, name="New"))
    r = await projects.update_project("p1", name="New")
    assert json.loads(route.calls[0].request.content) == {"name": "New"}
    assert r["project"]["name"] == "New"


async def test_delete_project_requires_confirm(api, guest):
    route = api.delete(API + "/projects/p1").respond(200, json={"ok": True})
    r = await projects.delete_project("p1")
    assert r["done"] is False and "confirm" in r["message"] and route.call_count == 0
    r = await projects.delete_project("p1", confirm=True)
    assert r["ok"] and r["archived"] and route.call_count == 1


async def test_get_credentials_shape(api, guest):
    api.get(API + "/projects/p1/credentials").respond(200, json={"hasSecret": True, "username": "bob"})
    assert await projects.get_project_credentials("p1") == {"has_secret": True, "username": "bob", "updated_at": None}


async def test_set_credentials_never_leaks_password(api, guest, caplog):
    caplog.set_level(logging.DEBUG)
    api.put(API + "/projects/p1/credentials").respond(200, json={"ok": True})
    r = await projects.set_project_credentials("p1", "bob", PASSWORD)
    assert r["stored_encrypted"] is True
    assert PASSWORD not in str(r) and PASSWORD not in caplog.text


async def test_set_credentials_error_does_not_echo_password(api, guest, caplog):
    caplog.set_level(logging.DEBUG)
    api.put(API + "/projects/p1/credentials").respond(500, text=f"crash while saving {PASSWORD}")
    with pytest.raises(KawachError) as ei:
        await projects.set_project_credentials("p1", "bob", PASSWORD)
    assert PASSWORD not in str(ei.value) and PASSWORD not in caplog.text


async def test_saved_tests_and_run_all(api, guest):
    api.get(API + "/projects/p1/saved-tests").respond(200, json=[
        {"id": "s1", "project_id": "p1", "name": "login", "tags": ["smoke"], "last_result": "passed", "script_path": "x"}])
    r = await projects.list_saved_tests("p1")
    assert r["saved_tests"][0]["last_result"] == "passed" and "script_path" not in r["saved_tests"][0]
    all_route = api.post(API + "/projects/p1/saved-tests/run-all").respond(200, json={"run_id": "run_9"})
    one_route = api.post(API + "/projects/p1/saved-tests/s1/run").respond(200, json={"run_id": "run_10"})
    assert (await projects.run_saved_tests("p1"))["run_id"] == "run_9"
    assert (await projects.run_saved_tests("p1", test_id="s1"))["run_id"] == "run_10"
    assert all_route.call_count == one_route.call_count == 1


async def test_delete_saved_test_guard(api, guest):
    route = api.delete(API + "/projects/p1/saved-tests/s1").respond(204)
    assert (await projects.delete_saved_test("p1", "s1"))["done"] is False
    assert route.call_count == 0
    assert (await projects.delete_saved_test("p1", "s1", confirm=True))["done"] is True


async def test_overview_composes(api, guest):
    api.get(API + "/projects/p1").respond(200, json=PROJECT)
    api.get(API + "/projects/p1/runs").respond(200, json=[
        {"runId": "r1", "stage": "done", "created_at": "2026-01-01"}, {"runId": "r2", "stage": "running", "created_at": "2026-02-01"}])
    api.get(API + "/projects/p1/saved-tests").respond(200, json=[{"id": "s1", "last_result": "passed"}, {"id": "s2"}])
    r = await projects.get_project_overview("p1")
    assert r["latest_runs"][0]["run_id"] == "r2"
    assert r["saved_tests"] == {"total": 2, "by_last_result": {"passed": 1, "never_run": 1}}
