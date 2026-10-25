# IMOCHA Run Report (checkpoint 1: Phase 0 partial, Phase 1 core)

Status legend: **LIVE** = executed against imocha.io with output; **LOCAL** = executed locally (no site traffic); **NOT RUN** = not executed.
No request has been sent to https://www.imocha.io/ so far. Everything below is LOCAL or code inspection.

## Phase 0: why the current output is useless

| Suspected cause | Verdict | Evidence |
|---|---|---|
| Spec parser treats the file as free text | **TRUE** (LOCAL, measured) | `parse_spec_text` on `QA_inputs/IMOCHA_SPEC.md` returned **148 items** with ids such as `Target`, `Mode`, `High`, `Priority`, `Steps`, `Expected`. Real REQ ids found: **0 of 17**. Real TC ids found: **0 of 46**. (`services/spec_parser.py`, regex `req_pattern` treats any `Word:` line as a requirement.) |
| Planner LLM invents generic tests | **TRUE by construction** (code) | `agents/planner/agent.py` `plan_catalog` fed the planner prompt the junk items above plus the app map, and asked an LLM for `min_tests=8` to `max_tests=12`. Nothing tied output to TC ids. |
| Explorer saw too little | **TRUE by config** (code), not observed live | `schemas/run.py` `Budgets`: `maxPages=10`, `exploreSeconds=90`, `maxTests=12`. The spec needs about 40 distinct URLs and 46 tests. A budget of 12 tests cannot hold 46 TCs. |
| Catalogs / saved tests keyed by URL only | **NOT VERIFIED** | `saved_test_service.py` and `catalog_service.py` not yet inspected. Phase 1.5 is still open. |
| Steps and expected results not structured | **PARTLY TRUE** (code) | `TestCase` had only `steps[].expected` (optional) and no list of expected results, no type/confidence/viewport, no spec hash. Fixed, see below. |
| Scripter writes assertions from imagination | **NOT VERIFIED** | Script writer not inspected or run yet. |
| Verdict engine / evidence problems | **NOT RUN** | Needs the benchmark gate (G9). |
| Phase 0 live baseline run (unmodified pipeline) | **NOT RUN** | I changed the parser before running the baseline. The 148-item measurement above stands in for the baseline. A true baseline needs the API server, an LLM key and browser. |

### Counts (LOCAL, after the new parser)
| Metric | Value |
|---|---|
| Spec REQ | 17 |
| Spec TC | 46 (the prompt said "about 45") |
| Parsed items, old parser | 148 (all junk) |
| Parsed REQ / TC, new parser | 17 / 46, 0 malformed blocks |
| Known observations / global rules parsed | 5 / 11 |
| Catalog tests mapped to a TC | 46 of 46 |
| TCs passing the quality lint, unedited | 46 of 46 |

## Phase 1: what is done

| Item | State |
|---|---|
| 1.1 Structured parser (`services/spec_structured.py`, `schemas/spec.py`) with spec hash, line-numbered errors, legacy bullet specs still work | **DONE, LOCAL** |
| 1.2 Spec-driven catalog: planner returns early to a deterministic builder when TC blocks exist; no LLM involved (`agents/planner/agent.py::_plan_spec_driven`, `services/spec_driven.py`) | **DONE, LOCAL** (not yet through a real run) |
| 1.3 Alignment endpoint `GET /runs/{id}/alignment`, start/resume blocked with HTTP 409 when TCs are missing, extra, altered or lint-failed | **DONE API, LOCAL**. UI banner NOT DONE. REQ -> TC -> script -> result -> evidence persistence NOT DONE. |
| 1.4 Lint at planning time | **DONE, LOCAL**. Lint verdict per test is stored on each catalog test; UI display NOT DONE. |
| 1.5 Catalog persistence keyed by (user, project, origin, spec hash) | **NOT DONE**. Only `meta.specHash` and `meta.catalogVersion` are stamped on the catalog. |

Tests: `apps/api/tests/test_spec_driven.py`, **9 passed**.
Full suite: 204 passed, 4 failed, 5 errors. The same failures (`test_a1_hardening` alembic/DB, `test_api::test_validation_errors_reported_together`, `test_scaffolding`) also occur with the working-tree changes stashed, so they predate this work. `test_commit_loop::test_saved_test_service_save_list_delete` was not compared against that baseline.

## Phases 2-6: NOT DONE / NOT RUN
- Phase 2 (project preset, URL-targeted explorer, per-TC viewport): not started.
- Phase 3 (one Playwright test per TC with `test.step`, helper use, read-only guard, shared rate limiter): not started.
- Phase 4 (calibration pass, `CALIBRATION_REPORT.md`, `IMOCHA_SPEC.calibrated.md`): not started. Needs live runs.
- Phase 5 (per-TC results, report, MCP numbers): not started.
- Phase 6 gates: G1 parser counts and lint **PASS (LOCAL)**; G2 alignment **PASS (LOCAL, catalog built from the parsed spec, not from a run)**; G3 to G9 **NOT RUN**.

No claims of success are made for anything marked NOT RUN.
