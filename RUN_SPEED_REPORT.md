# RUN_SPEED_REPORT: imocha run that "finished" with 0 specs

Evidence comes from `runs/20261025-045820-e7a6/pipeline.log` and `run.json` (the UI run), `runs/20261025-035304-616d` (same symptom), and my live proof runs. Everything marked LIVE ran against https://www.imocha.io/ with output; nothing here is claimed without it.

## 1. Root causes (with evidence)

| # | Symptom | Root cause | Evidence |
|---|---|---|---|
| 1 | "Dispatching 0 executable test specs", 1.4 s, "finished successfully", stage `done` | `StartTestForm` calls `createRun` and then `POST /runs/{id}/start` immediately. `/start` called `resume_run`, which set the stage to `scripting` and launched the execute graph while explore/plan had not even started. No catalog existed, so 0 specs ran, and the graph wrote `done`. | `e7a6` log: 04:58:20 "Initialized" and "Resuming execution pipeline" in the same second, "Dispatching 0" at 04:58:20, "finished successfully" 04:58:24. |
| 2 | "pre-suite gate check passed" logged AFTER the suite finished | The gate lives inside the explore node, which started in parallel with the premature execute graph. Execute never checked the gate. | `e7a6`: gate passed 04:58:29, five seconds after "finished successfully" 04:58:24. `stageTimes` shows `done` (04:58:24) before `exploring` (04:58:29). A late worker thread then moved a `done` run back to `exploring`. |
| 3 | 16.6 min of execution, never finished, UI still "running" | (a) `POST /runs/{id}/review` ran `run_execute()` synchronously inside the HTTP request and re-ran it on every review submission. The review was applied twice (05:01:52 and 05:02:22), so two Playwright runs (4 workers) hit the site at once. (b) The SSE stream loop was capped at `range(1200)` x 0.5 s = 10 min, then ended with no `run.done` event, so the UI kept showing "running". (c) `done_with_environment_issue` was not in `map_stage_to_status`, so it mapped to `created`. | `e7a6` log: "Batch review applied: 46 tests" twice; cancelled 05:19:14 (16.8 min after the second start). `streams.py` loop bound. |
| 4 | Where the 16.6 min went | The 46 scripts were slow because absent locators waited out the implicit timeout: `locator('main').innerText()` on pages with no `<main>` (about 30 s per page), and `getAttribute('aria-expanded')` on FAQ rows with no such attribute (15 s each). Trace screenshots plus video added up to 270 s of teardown on long tests. | calibration-1: TC-PAGE-001 328 s, PAGE-002 384 s, PAGE-004 333 s, PAGE-006 208 s (about 1250 s of 1895 s total). Profiling `main`: `locator.innerText: Timeout 30000ms`. |
| 5 | The earlier gate false-tripped ("timeout") on a healthy site | `diagnose_playwright.mjs` waits goto 25 s + load 10 s + networkidle 15 s (up to 50 s) but `circuit_breaker` killed it at 35 s. imocha never reaches networkidle. | `runs/20261025-053629-5108/environment_issue.json`. |
| 6 | Rate limiter let 3 requests into one 1 s window | Slot spacing was exactly 500 ms. | calibration-1: `peakRequestsInAnyOneSecondWindow: 3`. |

Not a cause here: LLM errors, rate limits or script-lint rejection. In spec-driven mode scripts are generated deterministically with 0 LLM calls (generation took 0.0 s in the proof run).

## 2. Fixes (files changed)

- **Fail loudly / state machine**: `domain/enums.py` (new stage `script_generation_failed`), `storage/artifacts.py` (`TERMINAL_STAGES`; a finished run can no longer go back to an active stage; `reopen_run` for retry; `fail_run(stage=...)`), `workflows/execute.py` (`_verify_scripts_or_fail`: approved>0 and scripts==0 means `script_generation_failed` with per-test reasons; refuses to report success when 0 selected tests executed), `api/v1/mappers/run_mapper.py` (stage mapping).
- **Single execution**: `services/run_service.py` `resume_run` is state-checked and idempotent (ignored while created/exploring/planning, while executing, and after finishing unless `retry`); `workflows/execute.py` `run_execute` is single-flight per run and ignores requests before plan/review; `api/v1/catalog.py` `submit_review` starts execution non-blocking and only when no test is still `proposed`.
- **Gate order**: `execution/circuit_breaker.py` persists `gate_result.json`; `run_execute` verifies the gate (and runs it if missing) and logs "gate verified before dispatch". Gate script timeouts fixed (`diagnose_playwright.mjs`, subprocess timeout 75 s).
- **UI status**: `api/v1/streams.py` streams until a terminal stage (heartbeat, no 10 min cap) and emits `run.done` for all terminal stages.
- **Speed**: `apps/runner/spec_driven/lib.ts` (5 s default timeout, `attr`/`mainText` without implicit waits, late consent banner auto-declined, limiter gap 600 ms), lighter trace (no per-action screenshots), per-test hard timeout 60 s (request-heavy tests get 60 s plus their request time at 2 req/s, `services/spec_budgets.py`), legacy `script_writer` runs with bounded concurrency = LLM key count and no fixed 1.2 s sleep, 90 s x 3 cap per script call, failures marked and skipped.
- **Explorer**: `agents/explorer/spec_explorer.py` + `spec_driven/snapshot.mjs` visit only the URLs the TCs need (32 distinct URLs) with a DOM + ARIA snapshot each, at the shared 2 req/s; a page budget below the need is raised and warned about instead of silently truncating.
- **Budgets**: `services/spec_budgets.py` (pages = distinct URLs + 10 %, per-stage time estimate), spec-driven defaults applied in `create_run`, `GET /runs/{id}/budgets` returns used vs needed per stage and warnings.
- **Priority tiers**: `selected_test_ids` (`P0`, `P0+P1`, `all`, `smoke` = first P0 TC per area); `priority_tier` on `POST /runs/{id}/review`, `tier` query on `/start` and `/resume`; the review gate has a "Run only priority" selector; a spec-driven run defaults to `P0`. Tests outside the tier are recorded as `not_run` ("outside the selected priority tier").
- Tests: `apps/api/tests/test_run_guards.py` (11 tests; 20 pass together with `test_spec_driven.py`). Full suite: 204 passed, the same 4 failed + 5 errors as before my changes (alembic/DB hardening, `test_validation_errors_reported_together`, scaffolding, `test_commit_loop`).

## 3. LIVE proof: P0 tier (run `20261025-054204-15cb`, real `create_run` pipeline)

The proof script reproduces the UI: `/start` straight after creation, then the review submitted and started twice.

| Check | Result |
|---|---|
| start right after create | ignored, stage stayed `created` |
| gate before anything | "Running pre-suite gate check" 05:42:04, "passed" 05:42:39, explorer starts after it |
| gate verified before dispatch | logged 05:43:35 |
| second start while executing | "Start request ignored: run is already 'scripting'" |
| selected tests | 12 (P0) |
| executed specs | **12 = 12** (the other 34 recorded as `not_run`) |
| final stage | `done` in run.json, API and `run.done` event |
| results | 8 passed, 4 failed (TC-NAV-005, NAV-006, NAV-008, FAQ-002) |

| Stage | Seconds |
|---|---|
| gate | 35 |
| explore (32 spec URLs) | 55.0 |
| plan | 0.0 |
| review gate (scripted) | 1.0 |
| scripting (deterministic) | 0.0 |
| **running (12 P0 tests, 2 workers)** | **191.0** |
| verify / report | 0.0 / 0.0 |
| **total wall** | **282.8** |

Target: P0 under 10 min. **Met: 3.2 min of execution, 4.7 min end to end.**
Politeness (this run): 35 gated requests, peak 2 in any 1 s window, 2 workers.

Before / after for the slow TCs: TC-PAGE-001 328 s to 28 s, TC-PAGE-002 384 s to 31 s.

## 4. LIVE: all tiers

All tiers (run `20261025-054706-caf8`, real pipeline, 46 of 46 specs executed, final stage `done`):

| Stage | Seconds |
|---|---|
| explore (32 spec URLs) | 78.0 |
| **running (46 tests, 2 workers)** | **614.0** |
| total wall (gate to report) | 726.0 (12.1 min) |

Target: all tests under 35 min. **Met: 10.2 min of execution, 12.1 min end to end.** Politeness: 187 gated requests, peak 2 in any 1 s window.
Outcome: 27 passed, 2 passed with issues, 11 failed, 4 script_error, 2 environment_error (`ERR_CONNECTION_TIMED_OUT` on TC-FOOT-002/003, site slow at that moment). The 4 script errors were caused by my 5 s default timeouts being too tight on a slow site (NAV-002/003 menu wait of 2 s, NAV-007 and PAGE-004 navigation). I raised element waits to 8 s, navigation to 30 s, menu waits to 3-4 s, and made FAQ/tab tests wait for the animation to finish. This all-tiers result was NOT re-run after that fix.

Smoke tier after the fix (run `20261025-055946-ebb7`): 7 of 7 executed, 6 passed, 1 failed (TC-UC-001, tab 2 text not found, not yet analysed). Execution 69 s, total 142.5 s, peak 2 req/s.

Summary of timings:

| Tier | Tests executed | Execution | Total wall |
|---|---|---|---|
| smoke | 7 | 69 s | 142 s |
| P0 | 12 | 191 s | 283 s |
| all | 46 | 614 s | 726 s |
| before (UI run e7a6) | 46 | never finished, cancelled at 16.8 min | n/a |

## 5. Known remaining issues (honest)

- 4 P0 failures in the P0 run are calibration items, not pipeline errors: NAV-005 (Customers page has no `<h1>`, plus slow navigation under the 5 s default; fix pending), NAV-006 (Login link `target=_blank` without `rel`), NAV-008 (Login / Book a Demo not in the mobile menu), FAQ-002 (second click fired during the open animation; fix pending).
- Editing Python files while `uvicorn --reload` is running restarts the API and marks in-flight runs `failed: Server restarted while the run was in progress` (this killed the state of my calibration run `20261025-045310-2306`).
- The cancel button only sets the stage; it does not kill the Playwright child process. Not changed here.
- The 60 s per-test limit is relaxed for request-heavy tests (TC-LINK-001, FOOT-004, PAGE-006, ...) because their requests alone need more than 60 s at 2 req/s.
- The 12 min per stage limit is not enforced as a fixed number for the run stage: the full suite needs more than 12 min by design at 2 req/s; the run stage timeout is derived from the estimate instead.
