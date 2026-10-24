"""End-to-end verification against a RUNNING KAWACH backend (nothing is mocked).

    python scripts/e2e.py --register-throwaway                  # registers two throwaway accounts on the backend
    KAWACH_EMAIL=.. KAWACH_PASSWORD=.. python scripts/e2e.py    # use your own account (+ KAWACH_OTHER_EMAIL/_PASSWORD for C)

Options: --base-url, --target (app under test, default http://localhost:4000), --spec (default: examples/target-app/spec.md),
--cap (max seconds to wait for a run, default 300), --scenario A|B|C|all.

Scenario A autonomous pipeline, B manual review gate, C failure modes. Prints PASS / FAIL / INCONCLUSIVE / SKIP per step
with timing. Exit code: 0 all good, 1 any FAIL, 2 no FAIL but something INCONCLUSIVE.
This script prints to stdout on purpose (it is a CLI script, not the MCP server).
"""

import argparse
import asyncio
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

import httpx
from pydantic import SecretStr

from kawach_mcp.client import KawachClient, get_client, set_client
from kawach_mcp.config import Settings
from kawach_mcp.errors import KawachError
from kawach_mcp.tools import bugs, catalog, observe, projects, reports, runs, system, workflow

ROOT = Path(__file__).resolve().parent.parent
RESULTS: list[tuple[str, str, str, float]] = []


class Ctx:
    async def report_progress(self, progress, total=None, message=None):
        pass

    async def info(self, message):
        pass


class Inconclusive(Exception):
    pass


class Skip(Exception):
    pass


async def step(name: str, fn):
    t0 = time.time()
    try:
        res = await fn()
        status, detail = "PASS", ""
    except Inconclusive as e:
        res, status, detail = None, "INCONCLUSIVE", str(e)
    except Skip as e:
        res, status, detail = None, "SKIP", str(e)
    except AssertionError as e:
        res, status, detail = None, "FAIL", f"assertion: {e}"
    except Exception as e:  # noqa: BLE001
        res, status, detail = None, "FAIL", f"{type(e).__name__}: {e}"
    dt = time.time() - t0
    RESULTS.append((name, status, detail, dt))
    print(f"{status:<13} {name}  ({dt:.1f}s)" + (f"  -> {detail}" if detail else ""), flush=True)
    return res


def make_client(base_url: str, email: str, password: str) -> KawachClient:
    return KawachClient(Settings(base_url=base_url, email=email, password=SecretStr(password), timeout_seconds=30))


def register(base_url: str, email: str, password: str) -> None:
    r = httpx.post(f"{base_url}/api/v1/auth/register", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"could not register throwaway account ({r.status_code}): {r.text[:150]}")


async def wait_done(run_id: str, cap: float, until=("done", "failed", "cancelled")) -> dict:
    t0 = time.time()
    while True:
        w = await observe.wait_for_run(run_id, Ctx(), until_stages=list(until), timeout_seconds=60, poll_seconds=3)
        if not w["still_running"]:
            return w
        if time.time() - t0 > cap:
            raise Inconclusive(f"cap of {cap:.0f}s reached while run {run_id} was still '{w['stage']}'")


def eq(a, b, msg=""):
    assert a == b, f"{msg} expected {b!r}, got {a!r}"


# ================================================================= Scenario A
async def scenario_a(args, st: dict) -> None:
    print("\n=== Scenario A: autonomous pipeline (LIVE) ===")
    h = await step("A1 health_check", lambda: system.health_check())
    assert h and h["status"] != "unreachable", "backend unreachable"
    await step("A1 check_target allows the target", lambda: _check_target(args.target))
    await step("A1 whoami shows the account", lambda: _whoami(st))
    proj = await step("A2 create temporary project", lambda: projects.create_project(f"e2e-{secrets.token_hex(3)}", args.target))
    if not proj:
        return
    st["project_id"] = proj["project"]["id"]
    st["cleanup_projects"].append(st["project_id"])

    spec = str(args.spec) if args.spec and Path(args.spec).exists() else None
    res = await step("A3 run_qa_pipeline (autonomous, max_pages=5)", lambda: workflow.run_qa_pipeline(
        Ctx(), project_id=st["project_id"], spec_file_path=spec, review_mode="autonomous", budgets={"max_pages": 5}, prompt="e2e", wait_seconds=100))
    if not res:
        return
    run_id = st["run_id"] = res["run_id"]
    st["cleanup_runs"].append(run_id)
    final = {"stage": res["stage"], "still_running": res["still_running"]}
    if res["still_running"]:
        w = await step("A3 wait_for_run until done (cap)", lambda: wait_done(run_id, args.cap))
        if not w:
            return
        final = w
    eq(final["stage"], "done", "run stage")
    await step("A3 run reached 'done'", lambda: _assert(final["stage"] == "done"))

    summary = await step("A4 get_run_summary", lambda: workflow.get_run_summary(run_id))
    if summary:
        print(f"      bugs: {summary['bugs']}  metrics: pass_rate={summary['metrics']['pass_rate_percent']} cost={summary['metrics']['estimated_cost_usd']}")
        print(f"      next: {summary['recommended_next_action']}")
        print(f"      top: {[ (b['id'], b['severity'], b['verification']) for b in summary['top_confirmed_bugs'] ]}")
    lb = await step("A4 list_bugs (verification shown for every bug)", lambda: _list_bugs(run_id))
    await step("A4 get_metrics", lambda: reports.get_metrics(run_id))
    await step("A4 get_report", lambda: _get_report(run_id))
    confirmed = [b for b in (lb or {}).get("bugs", []) if b["status"] == "confirmed"]
    st["confirmed"] = confirmed
    if confirmed:
        bid = confirmed[0]["id"]
        ctx_brief = await step("A5 get_bug_fix_context", lambda: _brief(run_id, bid))
        tmp = tempfile.mkdtemp(prefix="kawach_e2e_")
        await step("A5 save_repro_script (temp dir)", lambda: _save_script(run_id, bid, tmp))
        # a flaky or unverified bug must be refused by default
        other = [b for b in (lb or {})["bugs"] if b["status"] != "confirmed"]
        if other:
            await step("A5 fix brief refused for a non-confirmed bug", lambda: _refused(run_id, other[0]["id"]))
        _ = ctx_brief
    else:
        await step("A5 get_bug_fix_context / save_repro_script", lambda: _skip("no confirmed bug in this run"))
    await step("A6 compare_runs(run, run) shows 0 fixed / 0 new", lambda: _self_compare(run_id))
    await step("A7 export_report_markdown", lambda: _maybe(reports.export_report_markdown(run_id)))
    await step("A7 read_run_file('report.md')", lambda: _maybe(reports.read_run_file(run_id, "report.md", max_chars=300)))
    await step("A7 export_playwright_scripts (+extract)", lambda: _maybe(reports.export_playwright_scripts(run_id, extract_to="e2e_scripts")))
    await step("A7 export_run_archive", lambda: _maybe(reports.export_run_archive(run_id)))

    # retest + compare for real (the fix loop's last step)
    rt = await step("A8 retest_after_fix (same inputs, new run)", lambda: workflow.retest_after_fix(
        Ctx(), run_id, wait_seconds=100, spec_file_path=spec, allow_default_spec=spec is None))
    if rt:
        st["cleanup_runs"].append(rt["new_run_id"])
        if rt["still_running"]:
            await step("A8 wait for retest run", lambda: wait_done(rt["new_run_id"], args.cap))
        cmp_ = await step("A8 compare_runs(previous, retest)", lambda: workflow.compare_runs(run_id, rt["new_run_id"]))
        if cmp_:
            print(f"      verdict: {cmp_['verdict']}  {cmp_.get('matching_note', '')}")

    # saved regression tests (routes exist: saved-tests + run-all)
    async def regression():
        passed = [t for t in (await _tests(run_id)) if t.get("status") == "passed"]
        if not passed:
            raise Skip("no passed test to save")
        await projects.save_test_to_project(st["project_id"], run_id, passed[0]["id"], tags=["e2e"])
        r = await workflow.run_project_regression(Ctx(), st["project_id"], wait_seconds=100)
        if r["still_running"]:
            await wait_done(r["run_id"], args.cap)
        st["cleanup_runs"].append(r["run_id"])
        print(f"      regression run {r['run_id']}: stage={r['stage']} failures={r.get('failures')}")
        return r
    await step("A9 save_test_to_project + run_project_regression", regression)


# ================================================================= Scenario B
async def scenario_b(args, st: dict) -> None:
    print("\n=== Scenario B: manual review gate (LIVE) ===")
    if "project_id" not in st:
        p = await step("B0 create project", lambda: projects.create_project(f"e2e-b-{secrets.token_hex(3)}", args.target))
        if not p:
            return
        st["project_id"] = p["project"]["id"]
        st["cleanup_projects"].append(st["project_id"])
    spec = str(args.spec) if args.spec and Path(args.spec).exists() else None
    started = await step("B1 start_run (manual)", lambda: runs.start_run(project_id=st["project_id"], review_mode="manual", spec_file_path=spec, prompt="e2e review gate"))
    if not started:
        return
    rid = st["manual_run"] = started["run_id"]
    st["cleanup_runs"].append(rid)
    w = await step("B1 wait_for_run reaches awaiting_review", lambda: wait_done(rid, args.cap, until=("awaiting_review", "failed", "cancelled")))
    if not w:
        return
    eq(w["stage"], "awaiting_review", "stage")
    cat = await step("B2 get_catalog", lambda: catalog.get_catalog(rid))
    if not cat or not cat["tests"]:
        return
    before_ids = {t["id"] for t in cat["tests"]}
    added = await step("B2 add_test creates a NEW test (prompt-driven)", lambda: _add_test(rid, before_ids))
    cat2 = await catalog.get_catalog(rid)
    ids = [t["id"] for t in cat2["tests"]]
    added_id = (added or {}).get("test_id")
    reject_id = next((i for i in ids if i != added_id), ids[-1])
    await step("B3 gate refuses nothing unknown (unknown id lists valid ids)", lambda: _unknown_id(rid))
    await step(f"B3 review_tests rejects {reject_id} with a reason (rejections first)", lambda: catalog.review_tests(
        rid, [{"test_id": reject_id, "decision": "reject", "reason": "e2e: duplicate of another scenario"}]))
    r = await step("B3 approve_all_and_resume (single call, starts execution)", lambda: catalog.approve_all_and_resume(rid, "e2e approve"))
    if r:
        print(f"      approved {len(r['approved'])} test(s), stage now '{r['stage']}'")
    if r and r["stage"] != "done":
        await step("B4 wait_for_run until done", lambda: wait_done(rid, args.cap))
    async def rejected_not_run():
        tests = await _tests(rid)
        row = next((t for t in tests if t["id"] == reject_id), None)
        assert row is not None, "rejected test missing from execution list"
        assert row["status"] in ("queued", "skipped", "rejected", None), f"rejected test was executed (status {row['status']})"
        executed = [t for t in tests if t["status"] in ("passed", "failed")]
        return {"executed": len(executed), "rejected_status": row["status"]}
    await step("B4 rejected test was not executed", rejected_not_run)


# ================================================================= Scenario C
async def scenario_c(args, st: dict, other: tuple[str, str], mine: tuple[str, str]) -> None:
    print("\n=== Scenario C: failure modes (LIVE) ===")
    run_id = st.get("run_id") or st.get("manual_run")
    good = make_client(args.base_url, *mine)
    set_client(good)

    async def down():
        set_client(KawachClient(Settings(base_url="http://127.0.0.1:9", timeout_seconds=5)))
        h = await system.health_check()
        assert h["status"] == "unreachable", h
        try:
            await runs.get_run("x")
            raise AssertionError("get_run should fail when the backend is down")
        except KawachError as e:
            assert "Cannot reach the KAWACH backend" in str(e), str(e)
        finally:
            set_client(good)
        return "health_check -> unreachable; get_run -> 'Cannot reach' error"
    await step("C1 backend down / wrong base URL", down)

    async def bad_password():
        set_client(make_client(args.base_url, mine[0], "definitely-wrong-password"))
        try:
            await projects.list_projects()
            raise AssertionError("expected an auth error")
        except KawachError as e:
            assert "Authentication failed" in str(e), str(e)
            assert "definitely-wrong-password" not in str(e)
        finally:
            set_client(good)
        return "auth failure message, password not echoed"
    await step("C2 wrong password", bad_password)

    async def foreign_run():
        if not run_id:
            raise Skip("no run id available")
        set_client(make_client(args.base_url, *other))
        try:
            await runs.get_run(run_id)
            raise AssertionError("another account must not see this run")
        except KawachError as e:
            assert "Not found" in str(e), str(e)
        finally:
            set_client(good)
    await step("C3 another account's run id -> not found", foreign_run)

    async def outside_review():
        done = st.get("manual_run") or st.get("run_id")  # a finished MANUAL run: its gate is closed
        if not done:
            raise Skip("no finished run available")
        for call in (lambda: catalog.approve_all_and_resume(done), lambda: catalog.review_tests(done, [{"test_id": "T01", "decision": "approve"}], resume=True)):
            try:
                await call()
                raise AssertionError("review outside awaiting_review must be refused")
            except KawachError as e:
                assert "review gate is only open in 'awaiting_review'" in str(e) and "wait_for_run" in str(e), str(e)
    await step("C4 review action outside awaiting_review -> helpful stage message", outside_review)

    async def traversal():
        rid = st.get("run_id")
        if not rid:
            raise Skip("no run id available")
        tmp = Path(tempfile.mkdtemp(prefix="kawach_e2e_cwd_"))
        old = os.getcwd()
        os.chdir(tmp)
        try:
            for bad in ("../../escape", "../escape"):
                try:
                    await workflow.save_repro_script(rid, (st.get("confirmed") or [{"id": "B01"}])[0]["id"], dest_dir=bad)
                    raise AssertionError("save_repro_script traversal not refused")
                except KawachError as e:
                    assert "inside the current working directory" in str(e) or "Not found" in str(e), str(e)
            for bad in ("../x", "a/b", "/etc/passwd", ".."):
                try:
                    await reports.read_run_file(rid, bad)
                    raise AssertionError("read_run_file traversal not refused")
                except KawachError as e:
                    assert "plain file name" in str(e), str(e)
            r = await reports.export_playwright_scripts(rid, extract_to="../../outside")
            base = good.settings.download_dir.resolve()
            assert Path(r["extracted_to"]).resolve().is_relative_to(base), r
            art = await bugs.download_artifact(f"{good.base_url}/api/v1/runs/{rid}/files/run.json", filename="../../../evil.json")
            assert Path(art["path"]).resolve().is_relative_to(base), art
            assert not (tmp.parent / "escape").exists() and not (tmp.parent / "outside").exists()
        finally:
            os.chdir(old)
        return "save/read refused; extract and download stayed inside the download dir"
    await step("C5 path traversal in export/save/read tools refused", traversal)

    async def guards():
        rid = st.get("run_id") or st.get("manual_run")
        pid = st.get("project_id")
        if not rid or not pid:
            raise Skip("no run/project")
        for r in (await runs.delete_run(rid), await runs.cancel_run(rid), await projects.delete_project(pid)):
            assert r["done"] is False and "confirm" in r["message"], r
        assert (await runs.get_run(rid))["run_id"] == rid, "run must still exist"
        assert (await projects.get_project(pid))["id"] == pid, "project must still exist"
    await step("C6 confirm guards on delete/cancel (nothing changed)", guards)

    async def alive():
        h = await system.health_check()
        assert h["status"] != "unreachable"
    await step("C* server still healthy after all failure modes", alive)


# ----------------------------------------------------------------- helpers
async def _check_target(url):
    r = await system.check_target(url)
    assert r["verdict"] == "OK to test", r
    return r


async def _whoami(st):
    r = await system.whoami()
    assert r["authenticated"] and r["email"], r
    st["whoami"] = r["email"]
    return r


async def _assert(cond):
    assert cond


async def _skip(msg):
    raise Skip(msg)


async def _list_bugs(run_id):
    r = await bugs.list_bugs(run_id)
    for b in r["bugs"]:
        assert b["verification"], b
        if b["status"] == "confirmed":
            assert b["verification"] == "3/3 reproduced", b  # confirmed means 3/3 and nothing else
    print(f"      summary: {r['summary']}" + (f"\n      note: {r['honesty_note']}" if r.get("honesty_note") else ""))
    return r


async def _get_report(run_id):
    r = await reports.get_report(run_id)
    assert r["report"], r
    return r


async def _brief(run_id, bid):
    r = await workflow.get_bug_fix_context(run_id, bid)
    assert r["status"] == "confirmed" and "```" in r["brief"] and "Steps to reproduce" in r["brief"], r["brief"][:200]
    print(f"      brief for {bid}: page_path={r['page_path']!r}, {len(r['brief'])} chars")
    return r


async def _save_script(run_id, bid, tmp):
    old = os.getcwd()
    os.chdir(tmp)
    try:
        r = await workflow.save_repro_script(run_id, bid)
        assert Path(r["path"]).is_file() and Path(r["path"]).resolve().is_relative_to(Path(tmp).resolve())
        return r
    finally:
        os.chdir(old)


async def _refused(run_id, bid):
    try:
        await workflow.get_bug_fix_context(run_id, bid)
    except KawachError as e:
        assert "not confirmed" in str(e)
        return str(e)[:80]
    raise AssertionError("a non-confirmed bug got a fix brief")


async def _self_compare(run_id):
    r = await workflow.compare_runs(run_id, run_id)
    assert not r["fixed"] and not r["new"], r["verdict"]
    return r


async def _maybe(coro):
    """Exports may hit routes the backend does not have: that is a SKIP, not a failure."""
    try:
        return await coro
    except KawachError as e:
        if e.status_code == 404:
            raise Skip(f"route/file not available on this backend: {e}")
        raise


async def _tests(run_id):
    return await get_client().get(f"/runs/{run_id}/tests")


async def _add_test(rid, before_ids):
    r = await catalog.add_test(rid, "Empty form submission", "validation", "medium", "/signup",
                               [{"action": "Open /signup and submit with every field empty", "expected": "Validation errors are shown"},
                                {"action": "Check the page still shows the form"}], spec_ref=None)
    after = {t["id"] for t in (await catalog.get_catalog(rid))["tests"]}
    assert r["test_id"] and r["test_id"] in after and r["test_id"] not in before_ids, f"no new test created: {r}"
    return r


async def _unknown_id(rid):
    try:
        await catalog.review_tests(rid, [{"test_id": "T999", "decision": "approve"}], resume=True)
    except KawachError as e:
        assert "Unknown test id" in str(e) and "Valid ids" in str(e)
        return str(e)[:80]
    raise AssertionError("unknown id accepted")


async def cleanup(st, mine):
    print("\n=== Cleanup ===")
    set_client(make_client(mine[2], mine[0], mine[1]))
    for rid in dict.fromkeys(reversed(st["cleanup_runs"])):
        await step(f"cleanup delete_run {rid}", lambda rid=rid: runs.delete_run(rid, confirm=True))
    for pid in dict.fromkeys(st["cleanup_projects"]):
        await step(f"cleanup delete_project {pid[:8]}", lambda pid=pid: projects.delete_project(pid, confirm=True))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("KAWACH_BASE_URL", "http://localhost:8000"))
    ap.add_argument("--target", default="http://localhost:4000")
    ap.add_argument("--spec", default=str(ROOT.parent / "examples" / "target-app" / "spec.md"))
    ap.add_argument("--cap", type=float, default=300)
    ap.add_argument("--scenario", default="all", choices=["A", "B", "C", "all"])
    ap.add_argument("--register-throwaway", action="store_true")
    ap.add_argument("--no-cleanup", action="store_true")
    args = ap.parse_args()
    args.base_url = args.base_url.rstrip("/")

    if args.register_throwaway:
        tag = secrets.token_hex(3)
        mine = (f"e2e-main-{tag}@example.com", f"E2e-{secrets.token_hex(8)}!")
        other = (f"e2e-other-{tag}@example.com", f"E2e-{secrets.token_hex(8)}!")
        register(args.base_url, *mine)
        register(args.base_url, *other)
    else:
        mine = (os.environ["KAWACH_EMAIL"], os.environ["KAWACH_PASSWORD"])
        other = (os.environ.get("KAWACH_OTHER_EMAIL", ""), os.environ.get("KAWACH_OTHER_PASSWORD", ""))
        if not other[0]:
            register_other = f"e2e-other-{secrets.token_hex(3)}@example.com", f"E2e-{secrets.token_hex(8)}!"
            register(args.base_url, *register_other)
            other = register_other
    set_client(make_client(args.base_url, *mine))
    st = {"cleanup_runs": [], "cleanup_projects": []}
    t0 = time.time()
    try:
        if args.scenario in ("A", "all"):
            await scenario_a(args, st)
        if args.scenario in ("B", "all"):
            await scenario_b(args, st)
        if args.scenario in ("C", "all"):
            await scenario_c(args, st, other, mine)
    finally:
        if not args.no_cleanup:
            await cleanup(st, (mine[0], mine[1], args.base_url))
        await get_client().aclose()

    counts = {k: sum(1 for r in RESULTS if r[1] == k) for k in ("PASS", "FAIL", "INCONCLUSIVE", "SKIP")}
    print(f"\n=== SUMMARY ({time.time() - t0:.0f}s) === " + "  ".join(f"{k}: {v}" for k, v in counts.items()))
    for name, status, detail, _ in RESULTS:
        if status in ("FAIL", "INCONCLUSIVE", "SKIP"):
            print(f"  {status}: {name}  {detail}")
    return 1 if counts["FAIL"] else (2 if counts["INCONCLUSIVE"] else 0)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
