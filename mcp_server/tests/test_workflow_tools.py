import json

import httpx
import pytest

from kawach_mcp.errors import KawachError
from kawach_mcp.tools import observe, workflow
from conftest import API, BASE
from test_bug_tools import bug, mock_verifications, verification


class FakeCtx:
    def __init__(self):
        self.progress = []

    async def report_progress(self, progress, total=None, message=None):
        self.progress.append(message)

    async def info(self, message):
        pass


@pytest.fixture
def clock(monkeypatch):
    t = {"now": 0.0}

    async def fake_sleep(d):
        t["now"] += d

    monkeypatch.setattr(observe, "_now", lambda: t["now"])
    monkeypatch.setattr(observe, "_sleep", fake_sleep)
    return t


METRICS = {"wallClockSeconds": 60.0, "tests": {"planned": 10, "approved": 10, "passed": 7, "failed": 3, "errored": 0},
           "bugs": {"confirmed": 1}, "coverage": {"specItems": 10, "specItemsCovered": 9},
           "llm": {"calls": 1, "inputTokens": 1, "outputTokens": 1, "costUsd": 0.5}}


def run(rid="run_1", stage="done", **kw):
    return {"runId": rid, "id": rid, "stage": stage, "progress": 100, "review_mode": "autonomous",
            "targetUrl": "http://localhost:4000", "projectId": "p1", "prompt": "focus", "budgets": {"max_pages": 6},
            "counts": {"total_tests": 10}, **kw}


def mock_run(api, rid="run_1", stage="done", bugs=None, ver=None, metrics=METRICS, **kw):
    api.get(API + f"/runs/{rid}").respond(200, json=run(rid, stage, **kw))
    api.get(API + f"/runs/{rid}/execution").respond(200, json={"workers": [{"status": "running", "current_step": "Running T03"}]})
    if metrics is None:
        api.get(API + f"/runs/{rid}/metrics").respond(404, json={"detail": "x"})
    else:
        api.get(API + f"/runs/{rid}/metrics").respond(200, json=metrics)
    api.get(API + f"/runs/{rid}/bugs").respond(200, json=bugs or [])
    for bid, v in (ver or {}).items():
        route = api.get(BASE + f"/api/v1/runs/{rid}/files/verification/{bid}.json")
        route.respond(404, json={"detail": "nf"}) if v is None else route.respond(200, json=v)


def sbug(bid, status, sev, tid, rid="run_1", title=None):
    b = bug(bid, status, sev)
    b.update(run_id=rid, title=title or f"{tid}: problem {bid}",
             repro_script_url=f"/api/v1/runs/{rid}/files/scripts/{tid}.spec.ts")
    return b


R3, F2, NR = verification(True, True, True), verification(True, False, True), verification(False, False, False)


# ------------------------------------------------------------------ get_run_summary

async def test_summary_counts_only_verified_confirmed_and_sorts_top_bugs(api, guest):
    bugs = [sbug("B1", "confirmed", "low", "T1"), sbug("B2", "confirmed", "critical", "T2"), sbug("B3", "confirmed", "high", "T3"),
            sbug("B4", "confirmed", "medium", "T4"), sbug("B5", "confirmed", "low", "T5"), sbug("B6", "confirmed", "low", "T6"),
            sbug("B7", "flaky", "high", "T7"), sbug("B8", "not_reproduced", "high", "T8"), sbug("B9", "confirmed", "critical", "T9")]
    ver = {f"B{i}": R3 for i in (1, 2, 3, 4, 5, 6)} | {"B7": F2, "B8": NR, "B9": None}  # B9: labelled confirmed, no record
    mock_run(api, bugs=bugs, ver=ver)
    r = await workflow.get_run_summary("run_1")
    assert r["bugs"]["confirmed"] == 6 and r["bugs"]["flaky"] == 1 and r["bugs"]["not_reproduced"] == 1 and r["bugs"]["unverified"] == 1
    top = r["top_confirmed_bugs"]
    assert len(top) == 5 and [b["severity"] for b in top][:3] == ["critical", "high", "medium"]
    assert top[0]["verification"] == "3/3 reproduced: confirmed" and "B9" not in [b["id"] for b in top]
    assert r["metrics"]["total_tests"] == 10 and r["metrics"]["pass_rate_percent"] == 70.0 and r["metrics"]["spec_coverage_percent"] == 90.0
    assert r["metrics"]["estimated_cost_usd"] == 0.5 and r["metrics"]["failed"] == 3 and r["metrics"]["available"]
    assert r["recommended_next_action"] == "Call get_bug_fix_context for each confirmed bug."
    assert "NOT confirmed" in r["honesty_note"] and r["next_step_hint"] == r["recommended_next_action"]


@pytest.mark.parametrize("stage,expected", [
    ("created", "Call wait_for_run."), ("exploring", "Call wait_for_run."), ("planning", "Call wait_for_run."),
    ("scripting", "Call wait_for_run."), ("running", "Call wait_for_run."), ("verifying", "Call wait_for_run."),
    ("reporting", "Call wait_for_run."),
    ("awaiting_review", "Review the catalog (get_catalog), then review_tests or approve_all_and_resume."),
    ("failed", "Read get_logs(level='error'), then consider retry_run."),
    ("cancelled", "Run was cancelled; start a new run or retry_run."),
])
async def test_summary_recommended_action_by_stage_and_tolerates_missing_data(api, guest, stage, expected):
    mock_run(api, stage=stage, metrics=None)
    r = await workflow.get_run_summary("run_1")
    assert r["recommended_next_action"] == expected
    assert r["metrics"]["available"] is False and r["bugs"]["confirmed"] == 0


async def test_summary_done_without_confirmed_bugs(api, guest):
    mock_run(api, bugs=[sbug("B7", "flaky", "high", "T7")], ver={"B7": F2})
    r = await workflow.get_run_summary("run_1")
    assert r["recommended_next_action"] == "No confirmed defects; report flaky candidates honestly."
    assert r["bugs"]["flaky"] == 1 and "NOT confirmed defects" in r["honesty_note"]


# ------------------------------------------------------------------ get_bug_fix_context

def script_route(api, rid, tid, text="import { test } from '../../../apps/runner/fixtures';\ntest('x', async ({ page }) => { await page.goto('/signup'); });"):
    api.get(BASE + f"/api/v1/runs/{rid}/files/scripts/{tid}.spec.ts").respond(200, text=text)


async def test_fix_context_for_confirmed_bug_is_a_complete_brief(api, guest):
    b = sbug("B01", "confirmed", "high", "T02", title="T02: Signup accepts an invalid email")
    b["steps_to_reproduce"] = ["Navigate to /signup", "Enter invalid email", "Submit"]
    api.get(API + "/runs/run_1/bugs").respond(200, json=[b])
    mock_verifications(api, B01=R3)
    api.get(BASE + "/api/v1/runs/run_1/files/bugs.json").respond(200, json={"bugs": [{"id": "B01", "testId": "T02", "errorMessage": "expect(received).toHaveText"}]})
    script_route(api, "run_1", "T02")
    r = await workflow.get_bug_fix_context("run_1", "B01")
    brief = r["brief"]
    assert r["status"] == "confirmed" and r["page_path"] == "/signup" and r["severity"] == "high"
    for needle in ("# Fix brief: T02: Signup accepts an invalid email", "3/3 reproduced: confirmed", "/signup",
                   "1. Navigate to /signup", "**Expected:**", "**Actual:**", "expect(received).toHaveText", "TypeError: x",
                   "```ts", "page.goto('/signup')", "save_repro_script", "retest_after_fix", "Fix the root cause"):
        assert needle in brief, needle
    assert "WARNING" not in brief


async def test_fix_context_refuses_unconfirmed_unless_allowed(api, guest):
    flaky = sbug("B07", "flaky", "high", "T07")
    api.get(API + "/runs/run_1/bugs").respond(200, json=[flaky, sbug("B09", "confirmed", "high", "T09")])
    mock_verifications(api, B07=F2, B09=None)
    api.get(BASE + "/api/v1/runs/run_1/files/bugs.json").respond(404, json={"detail": "nf"})
    script_route(api, "run_1", "T07")
    with pytest.raises(KawachError, match="'flaky' \\(2/3 reproduced\\), not confirmed"):
        await workflow.get_bug_fix_context("run_1", "B07")
    with pytest.raises(KawachError, match="'unverified'"):  # backend label 'confirmed' without a real record
        await workflow.get_bug_fix_context("run_1", "B09")
    r = await workflow.get_bug_fix_context("run_1", "B07", allow_unconfirmed=True)
    assert r["brief"].startswith("**WARNING: this bug is FLAKY (2/3 reproduced). It is NOT a confirmed defect")


async def test_fix_context_page_path_from_app_map_and_nulls(api, guest):
    b = sbug("B10", "confirmed", "medium", "T10", title="T10: The settings page throws an error on load")
    b["steps_to_reproduce"] = ["Log in", "Open the settings page"]
    b["evidence"] = {}
    b["expected"] = b["actual"] = None
    api.get(API + "/runs/run_1/bugs").respond(200, json=[b])
    mock_verifications(api, B10=R3)
    api.get(BASE + "/api/v1/runs/run_1/files/bugs.json").respond(404, json={"detail": "nf"})
    api.get(BASE + "/api/v1/runs/run_1/files/scripts/T10.spec.ts").respond(404, json={"detail": "nf"})
    api.get(API + "/runs/run_1/app-map").respond(200, json={"pages": [{"url": "http://app/login"}, {"url": "http://app/settings"}]})
    r = await workflow.get_bug_fix_context("run_1", "B10")
    assert r["page_path"] == "/settings" and "script not available" in r["brief"] and "not recorded" in r["brief"]
    assert "Console errors: none" in r["brief"]


def test_guess_page_path_variants():
    g = workflow.guess_page_path
    assert g(["Go to /a/b-c"], None, []) == "/a/b-c"
    assert g([], "await page.goto('http://x.test/dash?x=1')", []) == "/dash"
    assert g(["click /cart now"], None, []) == "/cart"
    assert g(["nothing"], None, [], "") is None


# ------------------------------------------------------------------ save_repro_script

async def test_save_repro_script_is_safe_and_never_overwrites(api, guest, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b = sbug("B01", "confirmed", "high", "T02", title="T02: Signup accepts an invalid email!")
    api.get(API + "/runs/run_1/bugs").respond(200, json=[b])
    script_route(api, "run_1", "T02", text="FULL SCRIPT " * 2000)
    r = await workflow.save_repro_script("run_1", "B01")
    assert r["relative_path"] == "tests/kawach/B01-t02-signup-accepts-an-invalid-email.spec.ts"
    assert r["size_bytes"] == len("FULL SCRIPT " * 2000) and (tmp_path / r["relative_path"]).read_text() == "FULL SCRIPT " * 2000
    assert "npx playwright test tests/kawach/B01" in r["next_step_hint"]
    r2 = await workflow.save_repro_script("run_1", "B01")
    assert r2["relative_path"] == "tests/kawach/B01-t02-signup-accepts-an-invalid-email_1.spec.ts"
    (tmp_path / r["relative_path"]).write_text("old")
    r3 = await workflow.save_repro_script("run_1", "B01", overwrite=True)
    assert r3["relative_path"] == r["relative_path"] and (tmp_path / r["relative_path"]).read_text().startswith("FULL SCRIPT")
    r4 = await workflow.save_repro_script("run_1", "B01", filename="../../evil name")
    assert (tmp_path / "tests/kawach/evil_name.spec.ts").exists() and not (tmp_path.parent / "evil name").exists()
    assert "apps/runner/fixtures" not in r["path"]


async def test_save_repro_script_refuses_traversal_and_missing_script(api, guest, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    api.get(API + "/runs/run_1/bugs").respond(200, json=[sbug("B01", "confirmed", "high", "T02")])
    script_route(api, "run_1", "T02")
    for bad in ("../outside", "../../etc", "tests/../../x"):
        with pytest.raises(KawachError, match="inside the current working directory"):
            await workflow.save_repro_script("run_1", "B01", dest_dir=bad)
    with pytest.raises(KawachError, match="inside the current working directory"):
        await workflow.save_repro_script("run_1", "B01", dest_dir=str(tmp_path.parent))
    assert not list(tmp_path.parent.glob("outside*"))
    r = await workflow.save_repro_script("run_1", "B01", dest_dir=str(tmp_path / "abs_inside"))  # absolute but inside cwd: fine
    assert "abs_inside" in r["path"] and "apps/runner/fixtures" in (tmp_path / "abs_inside").glob("*").__next__().read_text()
    assert "note" in r  # warns about the runner fixtures import
    api.get(API + "/runs/run_1/bugs").respond(200, json=[sbug("B02", "confirmed", "high", "T03")])
    api.get(BASE + "/api/v1/runs/run_1/files/scripts/T03.spec.ts").respond(404, json={"detail": "nf"})
    with pytest.raises(KawachError, match="No repro script"):
        await workflow.save_repro_script("run_1", "B02")


# ------------------------------------------------------------------ compare_runs

def two_runs(api):
    a = [sbug("B01", "confirmed", "high", "T02", "run_a", "T02: Signup accepts invalid email"),
         sbug("B02", "confirmed", "high", "T03", "run_a", "T03:  Short  password accepted"),
         sbug("B03", "confirmed", "low", "T04", "run_a", "T04: Old problem"),
         sbug("B04", "flaky", "low", "T05", "run_a", "T05: Flaky one")]
    b = [sbug("B01", "confirmed", "high", "T02", "run_b", "t02: signup  accepts invalid email"),   # persisting (normalised)
         sbug("B02", "flaky", "high", "T03", "run_b", "T03: Short password accepted"),            # fixed, now flaky
         sbug("B09", "confirmed", "medium", "T09", "run_b", "T09: Brand new bug"),                # new
         sbug("B10", "flaky", "low", "T10", "run_b", "T10: Still flaky")]
    mock_run(api, "run_a", bugs=a, ver={"B01": R3, "B02": R3, "B03": R3, "B04": F2},
             metrics={**METRICS, "tests": {"planned": 10, "passed": 5, "failed": 5, "errored": 0}})
    mock_run(api, "run_b", bugs=b, ver={"B01": R3, "B02": F2, "B09": R3, "B10": F2})
    # verification routes are per run; the helper above registers them for the given run id


async def test_compare_runs_fixed_new_persisting_and_metrics(api, guest):
    two_runs(api)
    r = await workflow.compare_runs("run_a", "run_b")
    assert [b["title"] for b in r["persisting"]] == ["T02: Signup accepts invalid email"]
    assert [(b["id"], b["now"]) for b in r["fixed"]] == [("B02", "flaky"), ("B03", "absent")]
    assert [b["id"] for b in r["new"]] == ["B09"] and [b["id"] for b in r["still_flaky"]] == ["B02", "B10"] or len(r["still_flaky"]) == 2
    assert r["verdict"].startswith("2 fixed, 1 new, 1 persisting")
    assert r["metrics_delta"]["pass_rate_percent"] == {"before": 50.0, "after": 70.0, "change": 20.0}
    assert r["metrics_delta"]["confirmed_bugs"] == {"before": 3, "after": 2}
    assert "matching_note" not in r


async def test_compare_runs_self_compare_and_title_fallback(api, guest):
    two_runs(api)
    r = await workflow.compare_runs("run_a", "run_a")
    assert not r["fixed"] and not r["new"] and len(r["persisting"]) == 3 and r["verdict"].startswith("0 fixed, 0 new, 3 persisting")
    # same titles but renumbered test ids -> matched by title only, with a note
    c = [sbug("B01", "confirmed", "high", "T22", "run_c", "T02: Signup accepts invalid email")]
    mock_run(api, "run_c", bugs=c, ver={"B01": R3})
    r = await workflow.compare_runs("run_a", "run_c")
    assert [b["id"] for b in r["persisting"]] == ["B01"] and "matched by title only" in r["matching_note"]
    assert len(r["fixed"]) == 2 and not r["new"]


# ------------------------------------------------------------------ pipeline tools

CAT = [{"id": "T01", "title": "t", "priority": "high", "review_status": "pending", "spec_item_ids": ["S1"], "steps": ["a"]},
       {"id": "T02", "title": "t2", "priority": "low", "review_status": "pending", "spec_item_ids": ["S2"], "steps": ["a"]}]
CHECK_OK = {"allowed": True, "reachable": True, "status_code": 200, "reason": None}


async def test_pipeline_aborts_when_backend_down(api, guest):
    api.get(API + "/health").mock(side_effect=httpx.ConnectError("refused"))
    start = api.post(API + "/runs").respond(201, json=run())
    with pytest.raises(KawachError, match="Cannot reach the KAWACH backend"):
        await workflow.run_qa_pipeline(FakeCtx(), target_url="http://localhost:4000")
    assert start.call_count == 0


async def test_pipeline_aborts_when_target_blocked(api, guest):
    api.get(API + "/health").respond(200, json={"status": "active"})
    api.post(API + "/targets/check").respond(200, json={"allowed": False, "reachable": True, "reason": "no"})
    with pytest.raises(KawachError, match="Blocked by SSRF policy"):
        await workflow.run_qa_pipeline(FakeCtx(), target_url="http://evil.example")


async def test_pipeline_manual_mode_stops_at_review_and_says_so(api, guest, clock):
    api.get(API + "/health").respond(200, json={"status": "active"})
    api.post(API + "/targets/check").respond(200, json=CHECK_OK)
    api.get(API + "/config/defaults").respond(200, json={"limits": {}})
    post = api.post(API + "/runs").respond(201, json=run("run_1", "created", review_mode="manual"))
    mock_run(api, stage="awaiting_review", review_mode="manual", metrics=None)
    api.get(API + "/runs/run_1/catalog").respond(200, json=CAT)
    r = await workflow.run_qa_pipeline(FakeCtx(), target_url="http://localhost:4000", review_mode="manual")
    assert json.loads(post.calls[0].request.content)["review_mode"] == "manual"
    assert r["stage"] == "awaiting_review" and r["still_running"] is False
    assert r["awaiting_review"] == {"tests_total": 2, "tests_awaiting_review": 2}
    assert "STOPPED at awaiting_review" in r["message"] and "2 of 2" in r["message"] and "nothing has been executed" in r["message"]
    assert "review_tests" in r["next_step_hint"] and r["summary"]["stage"] == "awaiting_review"


async def test_pipeline_returns_still_running_instead_of_blocking(api, guest, clock):
    api.get(API + "/health").respond(200, json={"status": "active"})
    api.post(API + "/targets/check").respond(200, json=CHECK_OK)
    api.post(API + "/runs").respond(201, json=run("run_1", "created", review_mode="autonomous"))
    mock_run(api, stage="running", metrics=None)
    r = await workflow.run_qa_pipeline(FakeCtx(), target_url="http://localhost:4000", review_mode="autonomous", wait_seconds=7)
    assert r["still_running"] is True and "wait_for_run(run_id='run_1')" in r["next_step_hint"]
    assert r["elapsed_seconds"] <= 8 and r["summary"]["progress"]["step"] == "Running T03"


async def test_retest_refuses_when_spec_cannot_be_recovered(api, guest, clock):
    mock_run(api, "run_a")
    api.get(API + "/runs/run_a/catalog").respond(200, json=CAT)
    start = api.post(API + "/runs").respond(201, json=run("run_n"))
    with pytest.raises(KawachError, match="planned from a spec.*spec_file_path.*allow_default_spec"):
        await workflow.retest_after_fix(FakeCtx(), "run_a")
    assert start.call_count == 0


async def test_retest_recovers_inputs_and_returns_comparison(api, guest, clock):
    two_runs(api)
    api.get(API + "/runs/run_a/catalog").respond(200, json=CAT)
    api.post(API + "/targets/check").respond(200, json=CHECK_OK)
    api.get(API + "/config/defaults").respond(200, json={"limits": {"min_pages": 1, "max_pages": 100}})
    api.get(API + "/projects/p1").respond(200, json={"id": "p1", "targetUrl": "http://localhost:4000", "defaultMode": "autonomous"})
    post = api.post(API + "/runs").respond(201, json=run("run_b", "created"))
    r = await workflow.retest_after_fix(FakeCtx(), "run_a", allow_default_spec=True)
    body = json.loads(post.calls[0].request.content)
    assert body["target_url"] == "http://localhost:4000" and body["project_id"] == "p1" and body["review_mode"] == "autonomous"
    assert body["budgets"] == {"max_pages": 6} and body["prompt"] == "focus" and "spec_id" not in body
    assert r["new_run_id"] == "run_b" and r["comparison"]["verdict"].startswith("2 fixed, 1 new, 1 persisting")


async def test_retest_still_running_returns_new_run_id(api, guest, clock):
    mock_run(api, "run_a")
    api.get(API + "/runs/run_a/catalog").respond(200, json=[])
    api.post(API + "/targets/check").respond(200, json=CHECK_OK)
    api.get(API + "/config/defaults").respond(200, json={"limits": {"max_pages": 100}})
    api.get(API + "/projects/p1").respond(200, json={"id": "p1", "targetUrl": "http://localhost:4000", "defaultMode": "autonomous"})
    api.post(API + "/runs").respond(201, json=run("run_n", "created"))
    mock_run(api, "run_n", stage="verifying", metrics=None)
    r = await workflow.retest_after_fix(FakeCtx(), "run_a", wait_seconds=4)
    assert r["still_running"] and r["new_run_id"] == "run_n"
    assert r["next_step_hint"] == "wait_for_run('run_n'), then compare_runs('run_a', 'run_n')"


async def test_project_regression_runs_saved_tests_and_lists_failures(api, guest, clock):
    api.post(API + "/projects/p1/saved-tests/run-all").respond(200, json={"run_id": "run_r"})
    mock_run(api, "run_r")
    api.get(API + "/runs/run_r/tests").respond(200, json=[{"id": "T1", "title": "login", "status": "passed"},
                                                          {"id": "T2", "title": "cart", "status": "failed", "error_message": "expected 3 got 2"}])
    r = await workflow.run_project_regression(FakeCtx(), "p1")
    assert r["run_id"] == "run_r" and r["failures"] == [{"test": "T2: cart", "error": "expected 3 got 2"}]
    api.post(API + "/projects/p2/saved-tests/run-all").respond(200, json={"started": True})
    with pytest.raises(KawachError, match="did not return a run id"):
        await workflow.run_project_regression(FakeCtx(), "p2")
