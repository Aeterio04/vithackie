import asyncio
import json
import time

import httpx
import pytest

from kawach_mcp.errors import KawachError
from kawach_mcp.tools import observe
from conftest import API, BASE


class FakeCtx:
    def __init__(self, fail=False):
        self.progress, self.infos, self.fail = [], [], fail

    async def report_progress(self, progress, total=None, message=None):
        if self.fail:
            raise RuntimeError("client does not support progress")
        self.progress.append((progress, total, message))

    async def info(self, message):
        if self.fail:
            raise RuntimeError("nope")
        self.infos.append(message)


@pytest.fixture
def clock(monkeypatch):
    t = {"now": 0.0}

    async def fake_sleep(d):
        t["now"] += d

    monkeypatch.setattr(observe, "_now", lambda: t["now"])
    monkeypatch.setattr(observe, "_sleep", fake_sleep)
    return t


def run(stage, pct=0, mode="manual", **kw):
    return {"runId": "run_1", "stage": stage, "progress": pct, "review_mode": mode, **kw}


def seq_run(api, *items):
    it = iter(items)
    last = items[-1]

    def _se(req):
        try:
            v = next(it)
        except StopIteration:
            v = last
        return v if isinstance(v, httpx.Response) else httpx.Response(200, json=v)

    return api.get(API + "/runs/run_1").mock(side_effect=_se)


def execution(api, step="Crawling"):
    api.get(API + "/runs/run_1/execution").respond(200, json={"workers": [{"status": "running", "current_step": step}]})


CAT = [{"id": "T01", "title": "t", "priority": "high", "review_status": "pending", "steps": ["a"]}]


async def test_wait_returns_at_target_stage_with_catalog_counts(api, guest, clock):
    execution(api)
    api.get(API + "/runs/run_1/catalog").respond(200, json=CAT)
    seq_run(api, run("exploring", 10), run("planning", 35), run("awaiting_review", 50))
    r = await observe.wait_for_run("run_1", FakeCtx(), poll_seconds=3)
    assert r["still_running"] is False and r["stage"] == "awaiting_review"
    assert r["catalog_counts"] == {"total": 1, "by_status": {"proposed": 1}} and "review" in r["next_step_hint"]
    assert r["elapsed_seconds"] == 6.0


async def test_wait_emits_progress_only_on_change(api, guest, clock):
    execution(api, "Crawling")
    api.get(API + "/runs/run_1/catalog").respond(200, json=CAT)
    seq_run(api, run("exploring", 10), run("exploring", 10), run("exploring", 10), run("planning", 35), run("awaiting_review", 50))
    ctx = FakeCtx()
    await observe.wait_for_run("run_1", ctx)
    assert [p[2].split(":")[0] for p in ctx.progress] == ["exploring", "planning", "awaiting_review"]
    assert ctx.progress[0][:2] == (10.0, 100.0) and len(ctx.infos) == 3


async def test_wait_survives_client_without_progress_support(api, guest, clock):
    api.get(API + "/runs/run_1/logs").respond(200, json=[])
    seq_run(api, run("failed", 100))
    r = await observe.wait_for_run("run_1", FakeCtx(fail=True))
    assert r["stage"] == "failed" and r["still_running"] is False


async def test_wait_times_out_with_still_running_not_error(api, guest, clock):
    execution(api, "Running login test")
    seq_run(api, run("running", 70))
    r = await observe.wait_for_run("run_1", FakeCtx(), timeout_seconds=7, poll_seconds=3)
    assert r["still_running"] is True and r["stage"] == "running" and r["step"] == "Running login test"
    assert r["elapsed_seconds"] <= 7.5 and "wait_for_run again" in r["next_step_hint"]
    assert r["progress"] == {"stage": "running", "percent": 70, "step": "Running login test"}


async def test_wait_clamps_timeout_to_600(api, guest, clock):
    execution(api)
    seq_run(api, run("running", 70))
    r = await observe.wait_for_run("run_1", None, timeout_seconds=99999, poll_seconds=10)
    assert r["still_running"] is True and 590 <= r["elapsed_seconds"] <= 600


async def test_wait_done_digest(api, guest, clock):
    seq_run(api, run("done", 100, counts={"total_tests": 5, "passed_tests": 4, "failed_tests": 1}))
    api.get(API + "/runs/run_1/bugs").respond(200, json=[{"id": "B1", "status": "confirmed"}, {"id": "B2", "status": "confirmed"},
                                                          {"id": "B3", "status": "confirmed"}])

    def ok(*h):
        return {"attempts": [{"attempt": i, "reproduced": x, "durationMs": 5} for i, x in enumerate(h, 1)]}

    api.get(BASE + "/api/v1/runs/run_1/files/verification/B1.json").respond(200, json=ok(True, True, True))
    api.get(BASE + "/api/v1/runs/run_1/files/verification/B2.json").respond(200, json=ok(True, False, True))
    api.get(BASE + "/api/v1/runs/run_1/files/verification/B3.json").respond(404, json={"detail": "nf"})
    r = await observe.wait_for_run("run_1", None)
    assert r["digest"]["bugs"] == {"confirmed": 1, "flaky": 1, "not_reproduced": 0, "unverified": 1}
    assert r["digest"]["metrics"]["passed_tests"] == 4


async def test_wait_failed_gives_error_text(api, guest, clock):
    seq_run(api, run("failed", 100))
    api.get(API + "/runs/run_1/logs").respond(200, json=[
        {"level": "info", "source": "p", "message": "fine"}, {"level": "error", "source": "runner", "message": "Execution error: boom"}])
    r = await observe.wait_for_run("run_1", None)
    assert "Execution error: boom" in r["error"] and "retry_run" in r["next_step_hint"]


async def test_wait_returns_on_unexpected_terminal_stage(api, guest, clock):
    seq_run(api, run("cancelled", 100))
    api.get(API + "/runs/run_1/logs").respond(200, json=[])
    r = await observe.wait_for_run("run_1", None, until_stages=["awaiting_review"])
    assert r["still_running"] is False and "ended in 'cancelled'" in r["note"]


async def test_wait_retries_transient_errors(api, guest, clock):
    execution(api)
    api.get(API + "/runs/run_1/catalog").respond(200, json=CAT)
    route = seq_run(api, httpx.ConnectError("down"), httpx.Response(502, text="bad gateway"), run("awaiting_review", 50))
    # first two attempts fail transiently inside _retry, third succeeds
    route.side_effect = _side_effects([httpx.ConnectError("down"), httpx.Response(502, text="x"), httpx.Response(200, json=run("awaiting_review", 50))])
    r = await observe.wait_for_run("run_1", None)
    assert r["stage"] == "awaiting_review" and route.call_count == 3 and clock["now"] == 1.5  # 0.5 + 1.0 backoff


def _side_effects(items):
    it = iter(items)

    def se(req):
        v = next(it)
        if isinstance(v, Exception):
            raise v
        return v
    return se


async def test_wait_gives_up_after_three_transient_failures(api, guest, clock):
    route = api.get(API + "/runs/run_1").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(KawachError, match="Cannot reach"):
        await observe.wait_for_run("run_1", None)
    assert route.call_count == 3


async def test_wait_run_vanishes_404_fails_fast(api, guest, clock):
    route = api.get(API + "/runs/run_1").respond(404, json={"detail": "Run not found"})
    with pytest.raises(KawachError, match="Not found"):
        await observe.wait_for_run("run_1", None)
    assert route.call_count == 1


async def test_wait_rejects_bad_stage(guest):
    with pytest.raises(KawachError, match="Invalid until_stages"):
        await observe.wait_for_run("run_1", None, until_stages=["sleeping"])


# ---------------- tail_run_stream ----------------

def sse(*frames):
    return "".join(frames).encode()


def data(obj, event=None):
    return (f"event: {event}\n" if event else "") + f"data: {json.dumps(obj)}\n\n"


def stream_route(api, body, **kw):
    return api.get(API + "/runs/run_1/stream").respond(200, content=body, headers={"content-type": "text/event-stream"}, **kw)


async def test_tail_parses_frames_and_groups(api, guest):
    multiline = 'data: {"type": "log",\ndata: "source": "verifier", "message": "multi\\nline"}\n\n'
    body = sse(": keepalive comment\n\n", "event: ping\ndata: {}\n\n", multiline,
               data({"type": "run.status", "status": "exploring", "progress": 10}),
               data({"type": "test.update", "test": {"id": "T1", "title": "Login", "status": "passed", "duration_ms": 90}}),
               data({"type": "worker.update", "worker": {"id": "w1", "status": "running", "current_test_id": "T1", "current_step": "s"}}),
               data({"type": "budget.update", "usage": {"pages_crawled": 3}}),
               data({"type": "catalog.ready", "tests": [{}, {}]}),
               data({"type": "run.done", "run": {"stage": "done"}}),
               data({"type": "log", "source": "x", "message": "after done"}))
    stream_route(api, body)
    r = await observe.tail_run_stream("run_1", seconds=5, max_events=50)
    assert r["logs"] == ["[verifier] multi\nline"]  # ping and the post-run.done log are not counted
    assert r["stage_changes"] == [{"status": "exploring", "progress": 10}]
    assert r["tests"][0]["status"] == "passed" and r["budget"] == {"pages_crawled": 3}
    assert r["workers"]["w1"]["test"] == "T1" and r["catalog_tests"] == 2
    assert r["run_done"] is True and r["final_stage"] == "done" and r["events_seen"] == 7


async def test_tail_honours_event_limit(api, guest):
    stream_route(api, sse(*[data({"type": "log", "source": "s", "message": f"m{i}"}) for i in range(10)]))
    r = await observe.tail_run_stream("run_1", seconds=5, max_events=3)
    assert r["events_seen"] == 3 and r["logs"] == ["[s] m0", "[s] m1", "[s] m2"] and r["event_limit_reached"]


class HangingStream(httpx.AsyncByteStream):
    closed = False

    async def __aiter__(self):
        yield data({"type": "log", "source": "s", "message": "first"}).encode()
        try:
            await asyncio.sleep(3600)
        finally:
            HangingStream.closed = True


async def test_tail_honours_time_limit_and_never_hangs(api, guest):
    api.get(API + "/runs/run_1/stream").mock(return_value=httpx.Response(200, stream=HangingStream()))
    t0 = time.monotonic()
    r = await observe.tail_run_stream("run_1", seconds=1, max_events=50)
    assert time.monotonic() - t0 < 4
    assert r["time_limit_reached"] and r["logs"] == ["[s] first"] and r["run_done"] is False
    assert HangingStream.closed


class AbruptStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield data({"type": "log", "source": "s", "message": "partial"}).encode()
        raise httpx.RemoteProtocolError("peer closed connection without sending complete message body")


async def test_tail_server_close_mid_stream_is_not_an_error(api, guest):
    api.get(API + "/runs/run_1/stream").mock(return_value=httpx.Response(200, stream=AbruptStream()))
    r = await observe.tail_run_stream("run_1", seconds=5)
    assert r["logs"] == ["[s] partial"] and r["run_done"] is False


async def test_tail_clean_end_of_stream_and_404(api, guest):
    stream_route(api, b"")
    assert (await observe.tail_run_stream("run_1", seconds=2))["events_seen"] == 0
    api.get(API + "/runs/run_2/stream").respond(404, json={"detail": "Run not found"})
    with pytest.raises(KawachError, match="Not found"):
        await observe.tail_run_stream("run_2", seconds=2)


# ---------------- get_logs ----------------

def logs(n):
    return [{"level": "error" if i % 5 == 0 else "info", "source": "s", "message": f"m{i}"} for i in range(n)]


@pytest.mark.parametrize("n,limit,offset,tail,expected", [
    (0, 5, 0, True, []),
    (3, 5, 0, True, ["m0", "m1", "m2"]),            # total < limit
    (10, 3, 0, True, ["m7", "m8", "m9"]),
    (10, 3, 2, True, ["m5", "m6", "m7"]),           # skip two newest
    (10, 3, 9, True, ["m0"]),                       # window runs off the start
    (10, 3, 20, True, []),
    (10, 10, 0, True, [f"m{i}" for i in range(10)]),  # total == limit
    (10, 3, 0, False, ["m0", "m1", "m2"]),
    (10, 3, 8, False, ["m8", "m9"]),
])
async def test_get_logs_windows(api, guest, n, limit, offset, tail, expected):
    api.get(API + "/runs/run_1/logs").respond(200, json=logs(n))
    r = await observe.get_logs("run_1", limit=limit, offset=offset, tail=tail)
    assert [ln.split("] ")[1] for ln in r["lines"]] == expected
    assert r["total"] == n and r["showing"] == len(expected)


async def test_get_logs_level_filter(api, guest):
    api.get(API + "/runs/run_1/logs").respond(200, json=logs(10))
    r = await observe.get_logs("run_1", level="error")
    assert r["total"] == 2 and r["lines"] == ["[s] m0", "[s] m5"]


async def test_events_execution_and_app_map(api, guest):
    api.get(API + "/runs/run_1/events").respond(200, json=[
        {"id": "e1", "data": json.dumps({"type": "run.status", "status": "planning", "progress": 30})},
        {"id": "e2", "data": json.dumps({"type": "worker.update", "worker": {}})},
        {"id": "e3", "data": json.dumps({"type": "test.update", "test": {"id": "T1", "status": "failed"}})}])
    ev = await observe.get_events("run_1")
    assert [e["summary"] for e in ev["events"]] == ["status=planning progress=30", "T1 failed"]
    api.get(API + "/runs/run_1/execution").respond(200, json={
        "workers": [{"id": "w1", "name": "W1", "status": "running", "current_test_id": "T1", "current_step": "go"}],
        "tests": [{"id": "T1", "title": "Login", "status": "running", "worker_id": "w1"}, {"id": "T2", "status": "queued"}],
        "budget_usage": {"elapsed_minutes": 1.5}})
    ex = await observe.get_execution("run_1")
    assert ex["tests_by_status"] == {"running": 1, "queued": 1} and ex["active_tests"][0]["id"] == "T1"
    assert ex["elapsed_minutes"] == 1.5
    pages = [{"id": f"p{i}", "url": f"http://app/p{i}", "title": f"P{i}", "forms_count": 1, "interactive_elements": 4, "status_code": 200} for i in range(20)]
    api.get(API + "/runs/run_1/app-map").respond(200, json={"root_url": "http://app", "total_pages": 20, "pages": pages, "nodes": []})
    api.get(API + "/runs/run_1/files/app_map.json").respond(200, json={"summary": "A shop", "features": [{"name": "Cart"}]})
    m = await observe.get_app_map("run_1")
    assert len(m["pages"]) == 15 and m["truncated"] and m["total"] == 20 and m["total_forms"] == 20
    assert m["summary"] == "A shop" and m["features"] == ["Cart"] and m["pages"][0]["path"] == "/p0"
    assert len((await observe.get_app_map("run_1", detail="full"))["pages"]) == 20
    with pytest.raises(KawachError):
        await observe.get_app_map("run_1", detail="huge")
