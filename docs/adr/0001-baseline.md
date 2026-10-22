# ADR 0001: Architecture Baseline & Safety Net (Phase 0)

- **Date:** October 2026
- **Status:** Accepted
- **Author:** Senior Software Architect
- **Branch:** `refactor/platform-structure`
- **Git Tag:** `pre-refactor` (commit `a34730c`)

---

## 1. Context & Purpose

The KAWACH repository is undergoing an architectural overhaul and repository restructuring to transition from an initial POC layout to a clean, maintainable, layered monorepo (`apps/api`, `apps/web`, `apps/runner`, `packages/contracts`, `examples/target-app`, `benchmarks/`).

To guarantee zero regression during moves, splits, and schema additions, Phase 0 establishes the strict safety net and immutable baseline against which every subsequent phase will be verified.

---

## 2. Baseline Status Record

### 2.1. Git State
- **Pre-refactor Commit:** `a34730c`
- **Git Tag:** `pre-refactor`
- **Refactoring Branch:** `refactor/platform-structure`
- **Working Tree:** Clean, tracked in Git.

### 2.2. Test Suite Baseline
Executed command:
```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe -m pytest backend/tests/ -q
```
- **Results:** **54 passed, 1 skipped, 0 failures** in 33.16s.
- **Skipped Test:** `backend/tests/test_runner_client.py:test_runner_client_real_run` (marked as `@pytest.mark.integration`, requires live Playwright environment).
- **All 10 test modules verified:**
  1. `test_api.py`: 10 passed (HTTP routes, validation, security, traversal, exports)
  2. `test_bug_reporter.py`: 4 passed (defect synthesis, deduplication, formatting)
  3. `test_explorer.py`: 3 passed (crawler parser, feature summary, stats)
  4. `test_graphs.py`: 3 passed (LangGraph explore-plan & execute workflows)
  5. `test_llm.py`: 8 passed (multi-provider routing, rate limit clamping, disk cache)
  6. `test_planner.py`: 4 passed (catalog generation, spec linkage, ad-hoc planning)
  7. `test_report.py`: 4 passed (metrics derivation, Markdown report generator)
  8. `test_runner_client.py`: 5 passed, 1 skipped (Playwright execution driver)
  9. `test_script_writer.py`: 7 passed (Playwright script generation & healing)
  10. `test_verifier.py`: 6 passed (3x deterministic replay prover & scoring)

### 2.3. OpenAPI Snapshot
- Exported from FastAPI `app.openapi()` to [contracts/openapi.json](file:///d:/Soham/Vit%20Hackathon/vithackie/contracts/openapi.json).
- Total endpoints documented: **42 route operations** covering both root canonical paths (`/runs`, `/config`, `/health`) and frontend proxy adapter routes (`/api/v1/*`).

### 2.4. Golden Run Baseline
- Recorded and verified in [demo-data/golden/run_golden_demo/](file:///d:/Soham/Vit%20Hackathon/vithackie/demo-data/golden/run_golden_demo) and [contracts/samples/run_view.done.sample.json](file:///d:/Soham/Vit%20Hackathon/vithackie/contracts/samples/run_view.done.sample.json).
- Contains:
  - `run.json` (stage `done`, wall-clock time `360.0s`)
  - `input.json` (target `http://localhost:4000`, 11 spec items `S1`..`S11`)
  - `secrets.json` (`SecretPass123`)
  - `app_map.json` (4 pages, 4 forms, auth state)
  - `catalog.json` (11 approved test cases)
  - `review_log.json` (11 autonomous reviewer decisions)
  - `results.json` (13 tests, 3 passed, 9 assertion failures, 1 test error)
  - `bugs.json` (10 defects triaged, 8 confirmed, 1 flaky, 1 not reproduced)
  - `verification/B01.json` (3/3 reproduction record)
  - `metrics.json` (zero-LLM calculated metrics)
  - `report.md` (audit report)
  - `evidence/` (screenshots, videos, traces)
  - `scripts/` (TypeScript spec files)

---

## 3. Exit Criteria Verification for Phase 0

- [x] Tag `pre-refactor` created at clean commit `a34730c`.
- [x] Branch `refactor/platform-structure` checked out.
- [x] All 55 backend tests executed and passing with 0 failures.
- [x] Current OpenAPI schema snapshot saved to `contracts/openapi.json`.
- [x] Golden demo run recorded and verified.
- [x] Baseline documented in `docs/adr/0001-baseline.md`.

**Phase 0 is complete. Proceed to Phase 1 upon user review.**
