# QA Reliability & Pipeline Trustworthiness Report

This document records the discovery, root cause analyses, evidence, and benchmarks for the end-to-end overhaul of the KAWACH test execution, verification, and evidence pipeline.

---

## Phase 0: Pipeline Architecture Discovery

### 1. Pipeline Stages & Implementation Mapping

| Stage | Implementation File & Function | Subsystem / Agent | Inputs / Preconditions | Outputs / Produced Artifacts |
|---|---|---|---|---|
| **1. Explore** | `apps/api/src/kawach/workflows/explore_plan.py` (`node_explore`) &rarr; `apps/api/src/kawach/agents/explorer/agent.py` (`run_explorer`) &rarr; Subprocess `apps/runner/explore.ts` (`main`) | Chromium State-Graph Crawler | Target URL, auth credentials, crawl budgets (`maxPages`, `exploreSeconds`, `maxDepth=4`) | `runs/<id>/explore_raw.json`, `app_map.json` |
| **2. App Map Synthesis** | `apps/api/src/kawach/agents/explorer/agent.py` (`_summarize_app_map`) | LLM Agent | `explore_raw.json` graph, states, transitions, journeys | `runs/<id>/app_map.json` (Pages, headings, forms, buttons, deep journeys) |
| **3. Plan / Catalog** | `apps/api/src/kawach/workflows/explore_plan.py` (`node_plan`) &rarr; `apps/api/src/kawach/agents/planner/agent.py` (`plan_catalog`) | Planner Agent | `input.json` (spec items), `app_map.json` | `runs/<id>/catalog.json` (Multi-level test catalog: `single_step`, `journey`, `deep_path`, `edge_case`) |
| **4. Review Gate** | `apps/api/src/kawach/workflows/explore_plan.py` (`node_review_gate`) &rarr; `apps/api/src/kawach/agents/reviewer/agent.py` (`review_catalog`) | Rule-based Evaluator / Manual Gate | `catalog.json` | `runs/<id>/catalog.json` (tests marked approved/rejected), `review_log.json` |
| **5. Script Generation** | `apps/api/src/kawach/workflows/execute.py` (`node_write_scripts`) &rarr; `apps/api/src/kawach/agents/script_writer/agent.py` (`write_scripts`) | Scripter Agent | Approved tests in `catalog.json`, `spec`, `app_map.json` | `runs/<id>/scripts/<test_id>.spec.ts` |
| **6. Execution** | `apps/api/src/kawach/workflows/execute.py` (`node_run_tests`) &rarr; `apps/api/src/kawach/execution/runner.py` (`run_tests`, `run_playwright`) | Playwright Subprocess Runner | `scripts/*.spec.ts`, `apps/runner/playwright.config.ts`, `fixtures.ts` | `raw/test-results/main/`, `raw/playwright-main.json`, `results.json`, `evidence/<test_id>/` |
| **7. Bug Triage** | `apps/api/src/kawach/execution/triage.py` (`triage`) | Deterministic Triage Engine | `results.json`, `catalog.json` | `runs/<id>/bugs.json` (candidate defects de-duplicated by failing state & error signature), `repro/<bug_id>_repro.spec.ts` |
| **8. Bug Report Synthesis** | `apps/api/src/kawach/workflows/execute.py` (`node_report_bugs`) &rarr; `apps/api/src/kawach/agents/bug_reporter/agent.py` (`write_bug_reports`) | Bug Reporter LLM Agent | `bugs.json`, `evidence/<test_id>/console.json` | Updated `bugs.json` with structured reproduction steps, severity, category |
| **9. Verification & Replays** | `apps/api/src/kawach/workflows/execute.py` (`node_verify`) &rarr; `apps/api/src/kawach/execution/verifier.py` (`verify_all`, `verify_bug`) | Deterministic Replay Engine | `bugs.json`, `scripts/<test_id>.spec.ts` | `verification/<bug_id>.json` (3 replay trials), updated `bugs.json` (status: `confirmed`, `flaky`, `not_reproduced`) |
| **10. Reporting** | `apps/api/src/kawach/workflows/execute.py` (`node_build_report`) &rarr; `apps/api/src/kawach/execution/report_generator.py` (`generate_all_reports`) | Deterministic Report Engine | All run artifacts (`run.json`, `catalog.json`, `results.json`, `bugs.json`, `verification/*.json`) | `report.md`, `report.html`, `report.pdf`, `metrics.json` |

---

### 2. Test Script Generation, Execution & Status Computation

#### Script Production
- **Prompt & Template**: Scripts are generated individually via `apps/api/src/kawach/agents/script_writer/prompt.md`. The prompt includes `CANONICAL_EXAMPLE`, test metadata (`test_id`, `test_title`, `description`, `steps`), spec lines, and a compact app map string.
- **Selector & Expectation Vulnerabilities**:
  - The scripter is prompted to use `page.getByRole`, `page.getByLabel`, and `page.getByText`. However, the prompt encourages rigid text regexes (e.g. `/valid email/i` or `'Invalid credentials'`). When the app uses different wording (e.g., "Incorrect email or password"), the assertion fails.
  - The canonical example in `prompt.md` line 31 uses:
    `const hasAlert = await page.getByRole('alert').isVisible().catch(() => false);`
    `isVisible()` is an immediate point-in-time check without auto-waiting. If a toast appears after a network round-trip or animation (e.g., 1.5s delay), `isVisible()` returns `false` immediately.
  - In `apps/api/src/kawach/execution/runner.py` (lines 383-384), `clean_and_sanitize_script` forcibly replaces `waitForTimeout(N)` with `waitForLoadState()`. This strips explicit delays intended to wait for notifications or toasts.

#### Execution Architecture
- **Runner**: Executed via Node subprocess calling `npx playwright test --config playwright.config.ts`.
- **Config (`apps/runner/playwright.config.ts`)**:
  - `workers`: 2 (or from env).
  - `retries`: 0 (retries are handled in replay logic).
  - `timeout`: 30,000ms.
  - `actionTimeout`: 8,000ms.
  - `navigationTimeout`: 15,000ms.
  - `expect.timeout`: 5,000ms.
  - `viewport`: 1280x720.
  - `headless`: true.
  - `trace`: `'retain-on-failure'`.
  - `video`: `'retain-on-failure'` (Crucial: videos are NOT retained for passing tests).
- **Fixtures (`apps/runner/fixtures.ts`)**:
  - Provides `test`, `expect`, `credentials`, `unique`.
  - Implements route allow-list blocking off-domain requests.
  - Collects `consoleErrors`, `failedRequests`, `badResponses`, `visitedUrls`.
  - Attaches `console.json` and `network.json` via `testInfo.attach()` on teardown.

#### Outcome & Status Computation
- In `apps/api/src/kawach/execution/runner.py` (lines 544-550):
  ```python
  if status == "passed":
      outcome = "passed"
  elif is_assertion_failure(err_msg):
      outcome = "assertion_failure"
  else:
      outcome = "test_error"
  ```
- **Flaw**: Playwright marks a test `passed` if no uncaught exception or failed `expect` occurred in the test body. Even if the page threw an uncaught JS exception (`pageerror`), logged severe `console.error`s, or returned an HTTP 500 Internal Server Error, the test is marked `passed`! Furthermore, if a test contains zero assertions, it still passes.

---

### 3. Bug Creation and 3x Replay Verification

#### Bug Creation (`apps/api/src/kawach/execution/triage.py`)
- Candidate failures are filtered strictly on `t.outcome == "assertion_failure"`.
- Cleaned error messages are hashed into a signature: `f"{failing_state}::{err_sig}"`.
- Unique bugs are assigned IDs `B01`, `B02`, etc., and a minimal reproduction script is emitted to `repro/<bug_id>_repro.spec.ts`.

#### Verification Replays (`apps/api/src/kawach/execution/verifier.py`)
- Each candidate bug is replayed 3 times using `run_playwright` with `out_name=f"verify/{bug_id}/{attempt_num}"`.
- **Flaws in Verification**:
  1. **Deterministic Script Fallacy**: Replaying the exact same Playwright script 3 times only proves that the script fails deterministically. If the script asserted an incorrect string (e.g. "Invalid credentials" when the app says "Incorrect email or password"), the script fails 3 out of 3 times and is certified as a "Confirmed Bug" (False Positive).
  2. **Test Data Collision**: Replays execute without generating fresh credentials or unique usernames. If a test tests signup, attempt 1 might fail on validation, but if it succeeded, attempt 2 fails with "already registered".
  3. **No Control Check**: There is no second-opinion check on the page DOM or accessibility tree with relaxed oracle criteria before confirming.
  4. **No Replay Evidence Saved**: Replay video, trace, and screenshots are never preserved into `verification/` or `evidence/`.

---

### 4. Cross-Run State Leakage & Stale Data Analysis (Root Cause of S1)

An in-depth investigation identified several concrete mechanisms allowing stale findings to leak across runs:

1. **Hardcoded Fallback Spec (`apps/api/src/kawach/api/v1/runs.py` lines 128-134)**:
   ```python
   else:
       spec_file = settings.repo_root / "examples" / "target-app" / "spec.md"
       if not spec_file.exists():
           spec_file = settings.repo_root / "target-app" / "spec.md"
       if spec_file.exists():
           spec_raw = spec_file.read_text(encoding="utf-8")
   ```
   *Direct Evidence*: When pointing KAWACH at a new website without uploading an explicit spec text file, `runs.py` silently loaded `examples/target-app/spec.md`. That file contains specifications for an entirely different Todo/Settings dashboard app:
   - "S5: Logging in with a wrong password shows 'Invalid email or password'..."
   - "S8: On the dashboard, adding an item with an empty title is rejected with 'Title is required'..."
   - "S10: On the settings page, saving a display name shows 'Settings saved'..."
   The planner generated tests for these alien requirements; the runner asserted strings non-existent on the new shop; the tests failed; the verifier replayed and confirmed them 3/3 times!
2. **Project ID Fallback Reusing Unrelated Projects (`apps/api/src/kawach/api/v1/runs.py` lines 158-160)**:
   ```python
   elif user_projects:
       proj_id = user_projects[0].id
   ```
   If a new run omits `project_id`, instead of creating a scoped project for the new target, it attached the run to `user_projects[0]`. In `execute.py` (line 116), `svc.sync_run_tests(db_run.project_id, run_id)` mixed the tests and results into the older project's library.
3. **Lack of Target & Spec Content Fingerprinting**:
   Caches, saved tests, and verification files lacked a content hash of `(target_url, spec_content)`.
4. **Browser Origin State Reuse**:
   `fixtures.ts` only executed `context.clearCookies()`, failing to clear `localStorage`, `sessionStorage`, or IndexedDB between tests.

---

### 5. Evidence Production & Capture Timing

- **Screenshots**:
  - Live worker preview: Captured on frame navigation to `live/w{worker}.png`.
  - Teardown: Captured in `fixtures.ts` finally block to `live/{testId}.png`.
  - Failure moment screenshot: Captured by Playwright Test runner automatically when `screenshot: 'on'` / `'only-on-failure'` is configured.
- **Videos**:
  - Playwright records browser pages to temporary `.webm` files in `test-results/`.
  - Muxed continuously during execution, but finalized only when the context closes.
  - In Chromium, WebM recordings lack the EBML Segment duration header by default, causing players to display 0:00 / 0.1s.
- **Traces**:
  - Zip archives (`trace.zip`) created by Playwright on context disposal when configured.
- **Logs**:
  - `console.json` and `network.json` written in `fixtures.ts` finally block and attached to the Playwright test report.
  - Copied to `evidence/<test_id>/` in `runner.py` only if `outcome != "passed"`.

---

## Phase 1: Ground-Truth Benchmark & Baseline Scorecard

### 1. Benchmark Shop Implementation (`qa_benchmark/shop/`)
A deterministic e-commerce web application running on Node.js + Express (configurable port, default 3100) controlled via `BUGS=<comma-separated-list>` environment variable.

- **Pages**:
  - `/` (Home & Product Catalog with prices, categories, images)
  - `/products/:id` (Product details with telemetry and cart addition)
  - `/cart` (Cart summary, items, promo coupon module in Open Shadow DOM, customer support iframe)
  - `/login` (Authentication with delayed toast animation)
  - `/signup` (Account registration with native HTML5 validation)
  - `/checkout` (Order placement and payment gateway interaction)
  - `/api/reset` (Full state reset between test runs)

- **Known-Good Behaviors (K1 to K8 - Must NEVER be reported as bugs)**:
  - **K1**: Wrong password shows "Incorrect email or password" (wording difference from spec's "Invalid credentials").
  - **K2**: Error toast appears only after a 1.5-second animation delay.
  - **K3**: Signup utilizes native browser HTML5 validation (`:invalid` / `validationMessage`) for malformed email.
  - **K4**: Discount promo error feedback renders inside an open shadow root; customer support renders in an iframe.
  - **K5**: Cart subtotal and 10% tax calculation are mathematically exact; empty-cart checkout is rejected with descriptive message.
  - **K6**: Benign noise: Favicon 404 response and `console.info('Analytics initialized...')`.
  - **K7**: Cold start latency: 2-3s delay simulating server warm-up on initial request (`?slow=1`).
  - **K8**: Account reuse trap: Registering with an existing email (`seed.user@example.com`) displays conflict error.

- **Planted Defects (B1 to B8 - Toggled via `BUGS=...`)**:
  - **B1 (`login-no-error`)**: Wrong password submission displays no error message at all (Severity: High).
  - **B2 (`cart-total-wrong`)**: Cart subtotal calculation ignores item quantity when `quantity > 1` (Severity: High).
  - **B3 (`signup-accepts-invalid-email`)**: Malformed email without `@` is accepted on signup (Severity: Medium).
  - **B4 (`checkout-500`)**: Submitting checkout returns HTTP 500 Internal Server Error without UI feedback (Severity: Critical).
  - **B5 (`silent-console-error`)**: Product page loads visually but throws uncaught `TypeError` in console (Severity: Medium).
  - **B6 (`broken-image`)**: Product 2 image fails with HTTP 404 (Severity: Low).
  - **B7 (`flaky-random`)**: Product 1 "Add to Cart" button is omitted on 1 out of 3 requests (Expected Status: Flaky).
  - **B8 (`price-format`)**: Product 3 price renders as `$NaN` instead of numeric price (Severity: Medium).

- **Deterministic Probes (`qa_benchmark/probes/probes.spec.ts`)**:
  - 12 hand-written Playwright tests targeting K1–K8 and B1–B8 with known ground-truth expected outcomes.
  - Measured verdict engine independently of the LLM planner.

### 2. Baseline Scorecard (LIVE Execution on Unmodified Code)

Executed via `python scripts/run_benchmark.py --repeat 1` against the unmodified KAWACH platform:

```
========================================================================
                      BENCHMARK SCORECARD (BASELINE)
========================================================================
| Metric                                | Value            | Gate Target     | Status  |
|---------------------------------------|------------------|-----------------|---------|
| Probe Verdict Accuracy                | 100.0%           | 100%            | PASS    |
| Clean Shop False Positive Bugs        | 1                | 0               | FAIL    |
| Buggy Shop Defect Recall              | 0.0%             | >= 85%          | FAIL    |
| Buggy Shop Defect Precision           | 0.0%             | 100%            | FAIL    |
| Silent Passes (Uncaught Errors)       | 0                | 0               | PASS    |
| Valid Videos (Duration >= 1.5s)       | 0.0% (0/12 valid)| 100%            | FAIL    |
| Total Benchmark Execution Time        | 179.6s           | -               | -       |
========================================================================
```

#### Empirical Baseline Findings:
1. **False Positive Bug Fabricated on Clean Shop**:
   - Run `20261024-211859-9bb7` falsely reported and confirmed `B01: Login form allows submission with an empty email address` despite the application behaving correctly.
   - The generated script `T01.spec.ts` failed to clear prefilled input, asserted an invalid condition, failed, and was certified 3/3 by `verifier.py` without a control check.
2. **0% Defect Recall on Buggy Shop**:
   - The unmodified pipeline failed to detect and confirm any of the 8 planted defects (B1–B8).
3. **0% Video Evidence Validity**:
   - 0 out of 12 recorded WebM videos satisfied the evidence quality criteria. All videos suffered from missing duration metadata and were truncated or sub-second.
4. **Gates Failed at Baseline**: `G1 (Clean Shop False Positives)`, `G2 (Buggy Shop Defect Recall)`, `G6 (Video Duration Metadata)`.

