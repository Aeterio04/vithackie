import json

import httpx
import pytest

from kawach_mcp.errors import KawachError
from kawach_mcp.tools import catalog
from conftest import API


def T(i, status="pending", priority="high"):
    return {"id": f"T{i:02d}", "title": f"Test {i}", "spec_item_ids": [f"S{i}"], "steps": ["click: a", "fill: b"],
            "expected_result": f"works {i}", "priority": priority, "review_status": status, "source": "llm"}


CAT = [T(1), T(2), T(3, "approved", "low"), T(4, "rejected", "medium")]
RUN = {"runId": "run_1", "stage": "awaiting_review", "review_mode": "manual"}


@pytest.fixture
def run_ar(api):
    api.get(API + "/runs/run_1").respond(200, json=RUN)
    api.get(API + "/runs/run_1/catalog").respond(200, json=CAT)


async def test_get_catalog_counts_and_spec_coverage(api, guest, run_ar):
    r = await catalog.get_catalog("run_1")
    assert r["counts"]["by_status"] == {"proposed": 2, "approved": 1, "rejected": 1}
    assert r["counts"]["by_priority"] == {"high": 2, "low": 1, "medium": 1}
    assert r["spec_coverage"]["spec_refs"] == ["S1", "S2", "S3", "S4"]
    assert r["tests"][0]["step_count"] == 2 and "steps" not in r["tests"][0]
    assert "2 test(s) await a decision" in r["next_step_hint"]


async def test_get_catalog_filters_and_steps_cap(api, guest):
    many = [T(i) for i in range(1, 31)]
    api.get(API + "/runs/run_1/catalog").respond(200, json=many)
    r = await catalog.get_catalog("run_1", status="proposed", include_steps=True)
    assert len([t for t in r["tests"] if "steps" in t]) == 25
    assert any("first 25" in n for n in r["notes"])
    r = await catalog.get_catalog("run_1", priority="low")
    assert r["count"] == 0
    with pytest.raises(KawachError, match="Invalid status"):
        await catalog.get_catalog("run_1", status="pending")


async def test_get_catalog_not_generated_yet(api, guest):
    api.get(API + "/runs/run_1/catalog").respond(200, json=[])
    api.get(API + "/runs/run_1").respond(200, json=dict(RUN, stage="exploring"))
    r = await catalog.get_catalog("run_1")
    assert "awaiting_review" in r["message"] and r["tests"] == []


async def test_get_test_unknown_lists_valid_ids(api, guest, run_ar):
    assert (await catalog.get_test("run_1", "T02"))["steps"] == ["click: a", "fill: b"]
    with pytest.raises(KawachError, match="Valid ids: T01, T02, T03, T04"):
        await catalog.get_test("run_1", "T99")


# ---- review gate ----

async def test_review_refused_outside_awaiting_review(api, guest):
    api.get(API + "/runs/run_1").respond(200, json=dict(RUN, stage="running"))
    post = api.post(API + "/runs/run_1/review").respond(200, json={})
    with pytest.raises(KawachError) as ei:
        await catalog.review_tests("run_1", [{"test_id": "T01", "decision": "approve"}], resume=True)
    assert str(ei.value) == ("Run run_1 is in stage 'running'; the review gate is only open in "
                             "'awaiting_review'. Use wait_for_run to wait for it.")
    assert post.call_count == 0


async def test_review_autonomous_explained(api, guest):
    api.get(API + "/runs/run_1").respond(200, json=dict(RUN, stage="running", review_mode="autonomous"))
    with pytest.raises(KawachError, match="reviewer agent"):
        await catalog.approve_all_and_resume("run_1")


@pytest.mark.parametrize("decisions,kw,msg", [
    ([{"test_id": "T99", "decision": "approve"}], {"resume": True}, "Unknown test id.*T99.*Valid ids: T01"),
    ([{"test_id": "T01", "decision": "reject"}], {}, "reason is required to reject test T01"),
    ([{"test_id": "T01", "decision": "approve"}, {"test_id": "T01", "decision": "reject", "reason": "x"}], {}, "Duplicate decision"),
    ([{"test_id": "T01", "decision": "maybe"}], {}, "decision 'approve' or 'reject'"),
    ([], {}, "must not be empty"),
    ([{"test_id": "T01", "decision": "reject", "reason": "dup"}, {"test_id": "T02", "decision": "reject", "reason": "dup"}],
     {"resume": True}, "empty approved set"),
])
async def test_review_validation_before_any_post(api, guest, run_ar, decisions, kw, msg):
    post = api.post(API + "/runs/run_1/review").respond(200, json={})
    api_cat = CAT  # T03 stays approved, so for the 'empty approved' case reject it too
    if "empty approved" in msg:
        decisions = decisions + [{"test_id": "T03", "decision": "reject", "reason": "dup"}]
    with pytest.raises(KawachError, match=msg):
        await catalog.review_tests("run_1", decisions, **kw)
    assert post.call_count == 0 and api_cat is CAT


async def test_review_requires_resume_when_something_gets_approved(api, guest, run_ar):
    post = api.post(API + "/runs/run_1/review").respond(200, json={})
    with pytest.raises(KawachError, match="resume=True"):
        await catalog.review_tests("run_1", [{"test_id": "T01", "decision": "approve"}])
    assert post.call_count == 0


async def test_review_sends_rejects_first_then_approves(api, guest):
    stages = iter([RUN, dict(RUN, stage="scripting")])
    api.get(API + "/runs/run_1").mock(side_effect=lambda r: httpx.Response(200, json=next(stages)))
    api.get(API + "/runs/run_1/catalog").respond(200, json=CAT)
    post = api.post(API + "/runs/run_1/review").respond(200, json={"applied_count": 1, "run_status": "awaiting_review"})
    r = await catalog.review_tests("run_1", [
        {"test_id": "T01", "decision": "approve", "reason": "good"},
        {"test_id": "T02", "decision": "reject", "reason": "duplicate"},
        {"test_id": "T03", "decision": "approve"}], resume=True)
    bodies = [json.loads(c.request.content) for c in post.calls]
    assert bodies == [{"test_ids": ["T02"], "decision": "rejected", "reason": "duplicate"},
                      {"test_ids": ["T01"], "decision": "approved", "reason": "good"}]
    assert r["approved"] == ["T01"] and r["rejected"] == ["T02"] and r["unchanged"] == ["T03"]
    assert r["decisions_count"] == 3 and r["stage"] == "scripting" and r["ok"]


async def test_approve_all_and_resume_single_post(api, guest, run_ar):
    stages = iter([dict(RUN, stage="scripting")])
    post = api.post(API + "/runs/run_1/review").respond(200, json={"applied_count": 2, "run_status": "executing"})
    api.get(API + "/runs/run_1").mock(side_effect=[httpx.Response(200, json=RUN), httpx.Response(200, json=next(stages))])
    r = await catalog.approve_all_and_resume("run_1", reason="lgtm")
    assert post.call_count == 1
    assert json.loads(post.calls[0].request.content) == {"test_ids": ["T01", "T02"], "decision": "approved", "reason": "lgtm"}
    assert r["approved"] == ["T01", "T02"] and r["already_approved"] == ["T03"] and r["stage"] == "scripting"


async def test_reject_tests_refuses_when_others_approved(api, guest, run_ar):
    post = api.post(API + "/runs/run_1/review").respond(200, json={})
    with pytest.raises(KawachError, match="already approved"):
        await catalog.reject_tests("run_1", ["T01"], "dup")
    assert post.call_count == 0


async def test_reject_tests_ok_when_nothing_approved(api, guest):
    cat = [T(1), T(2)]
    api.get(API + "/runs/run_1").respond(200, json=RUN)
    api.get(API + "/runs/run_1/catalog").respond(200, json=cat)
    post = api.post(API + "/runs/run_1/review").respond(200, json={})
    r = await catalog.reject_tests("run_1", ["T01", "T02"], "out of scope")
    assert post.call_count == 1 and r["rejected"] == ["T01", "T02"]


async def test_update_test_validation_and_patch_body(api, guest, run_ar):
    with pytest.raises(KawachError, match="Nothing to update"):
        await catalog.update_test("run_1", "T01")
    with pytest.raises(KawachError, match="Invalid priority"):
        await catalog.update_test("run_1", "T01", priority="urgent")
    with pytest.raises(KawachError, match="reason is required"):
        await catalog.update_test("run_1", "T01", status="rejected")
    patch = api.patch(API + "/runs/run_1/catalog/T01").respond(200, json=T(1))
    r = await catalog.update_test("run_1", "T01", title="New", description="exp", steps=["a", "b"], priority="critical")
    assert json.loads(patch.calls[0].request.content) == {
        "title": "New", "expected_result": "exp", "steps": ["a", "b"], "priority": "critical"}
    assert r["test"]["id"] == "T01"


async def test_update_test_status_goes_through_review_and_is_idempotent(api, guest, run_ar):
    post = api.post(API + "/runs/run_1/review").respond(200, json={})
    r = await catalog.update_test("run_1", "T03", status="approved")  # already approved
    assert post.call_count == 0 and "already approved" in r["unchanged"]
    await catalog.update_test("run_1", "T04", status="approved")
    assert json.loads(post.calls[0].request.content)["decision"] == "approved"
    with pytest.raises(KawachError, match="cannot move a test back"):
        await catalog.update_test("run_1", "T03", status="proposed")


async def test_add_test_validation_and_prompt(api, guest, run_ar):
    base = dict(run_id="run_1", title="Login lockout", category="security", priority="high", page_path="/login")
    with pytest.raises(KawachError, match="at least 2 steps"):
        await catalog.add_test(**base, steps=[{"action": "x"}])
    with pytest.raises(KawachError, match="Step 2 has an empty action"):
        await catalog.add_test(**base, steps=[{"action": "x"}, {"action": " "}])
    post = api.post(API + "/runs/run_1/catalog/test").respond(200, json=T(5))
    r = await catalog.add_test(**base, spec_ref="S3", steps=[{"action": "enter bad password 5 times", "expected": "locked"}, {"action": "login"}])
    prompt = json.loads(post.calls[0].request.content)["prompt"]
    assert "Login lockout" in prompt and "/login" in prompt and "S3" in prompt
    assert "1. enter bad password 5 times -> expect: locked" in prompt and "2. login" in prompt
    assert r["test_id"] == "T05" and "proposed" in r["next_step_hint"]


async def test_review_log(api, guest):
    api.get(API + "/runs/run_1/review-log").respond(200, json=[
        {"test_id": "T01", "decision": "rejected", "actor": "human", "reason": "dup", "at": "t"}])
    r = await catalog.get_review_log("run_1")
    assert r["decisions"][0]["reason"] == "dup"


async def test_review_timeout_is_submitted_not_an_error(api, guest, run_ar):
    """Live finding: POST /review runs the whole pipeline synchronously; a slow run must not look like a failure."""
    api.post(API + "/runs/run_1/review").mock(side_effect=httpx.ReadTimeout("slow"))
    r = await catalog.approve_all_and_resume("run_1")
    assert r["ok"] and "timed out while it kept running" in r["note"]
    r = await catalog.review_tests("run_1", [{"test_id": "T01", "decision": "approve"}], resume=True)
    assert r["ok"] and "wait_for_run" in r["note"]


async def test_review_other_errors_still_raise(api, guest, run_ar):
    api.post(API + "/runs/run_1/review").respond(500, text="kaput")
    with pytest.raises(KawachError, match="Backend error"):
        await catalog.approve_all_and_resume("run_1")
