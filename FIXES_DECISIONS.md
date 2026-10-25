# Engineering Decisions and Bug Fixes Log (KAWACH)

This document tracks all discoveries, root causes, architectural decisions, and verification proofs for:
1. Groq Rate Limits -> Strict Round-Robin Multi-Key Pool
2. Reliable Final Report Generation (Markdown + PDF)

---

## PROBLEM 1: GROQ RATE LIMITS -> STRICT ROUND-ROBIN MULTI-KEY POOL

### Phase 1A: Discovery

#### 1. LLM Call Sites in the Backend
| File | Function / Class | Agent / Subsystem | Sync / Async | Streaming | Purpose |
|---|---|---|---|---|---|
| `apps/api/src/kawach/agents/explorer/agent.py` | `_summarize_app_map` | Explorer Agent | Sync | No | Summarizes explored pages & extracts features (JSON) |
| `apps/api/src/kawach/agents/planner/agent.py` | `plan_catalog` | Planner Agent | Sync | No | Generates initial test catalog from app map and spec (JSON) |
| `apps/api/src/kawach/agents/planner/agent.py` | `plan_catalog` (retry loop) | Planner Agent | Sync | No | Retries missing high-risk spec coverage (JSON) |
| `apps/api/src/kawach/agents/planner/agent.py` | `plan_single_test` | Planner Agent | Sync | No | Plans a single test for targeted spec items (JSON) |
| `apps/api/src/kawach/agents/script_writer/agent.py` | `generate_script` | Scripter Agent | Sync | No | Synthesizes Playwright TypeScript test script (Text) |
| `apps/api/src/kawach/agents/script_writer/agent.py` | `repair_script` | Scripter Agent | Sync | No | Self-repairs failed test script compilation (Text) |
| `apps/api/src/kawach/agents/bug_reporter/agent.py` | `report_bugs` | Bug Reporter Agent | Sync | No | Analyzes execution failures and drafts bug reports (JSON) |
| `apps/api/src/kawach/execution/runner.py` | `_self_heal_script` | Runner / Execution | Sync | No | Attempts runtime self-healing of selector/assertion errors (Text) |
| `apps/api/src/kawach/llm/client.py` | `LLM._call_provider` | Core LLM Provider Dispatcher | Sync | No | Dispatches to GroqHandler, OpenAI, Anthropic, Gemini |
| `apps/api/src/kawach/llm/groq_handler.py` | `GroqHandler.complete` | Groq Handler Engine | Sync | No | Calls Groq via `openai.OpenAI.chat.completions.create` |
| `apps/api/app/llm.py` | `LLM._call_provider` | Legacy Compatibility Shim | Sync | No | Direct `chat.completions.create` |
| `apps/api/app/agents/script_writer.py` | `generate_script`, `repair_script` | Legacy Scripter Shim | Sync | No | Forwards to LLM client |
| `apps/api/app/agents/bug_reporter.py` | `report_bugs` | Legacy Reporter Shim | Sync | No | Forwards to LLM client |
| `apps/api/app/runner_client.py` | `_self_heal_script` | Legacy Runner Client | Sync | No | Forwards to LLM client |
| `fix_pipeline/src/kawach_fix/clients/llm.py` | `HttpxGroqClient.generate` | Fix Pipeline Subsystem | Async | No | Direct `httpx.post` to `https://api.groq.com/openai/v1/chat/completions` |
| `kawach_demo/src/kawach_demo/llm_chain.py` | `LLMChain._call_groq` | Standalone Demo Script | Async | No | Direct `httpx.post` to `https://api.groq.com/openai/v1/chat/completions` |

*Note on Reviewer & Verifier Agents:*
- Reviewer (`kawach/agents/reviewer/agent.py`) is deterministic/rule-based; it approves/rejects tests based on criteria (depth, steps, title) and makes 0 LLM calls.
- Verifier (`kawach/execution/verifier.py`) is deterministic replay using Playwright runner (3 trials); it makes 0 LLM calls.

#### 2. Key Reading & Existing Rate Limit / Retry Logic
- **Key Resolution Today:**
  - `apps/api/src/kawach/core/config.py`: `GROQ_API_KEY: str = ""` read via `Settings(BaseSettings)` from `.env` or `apps/api/.env`.
  - `apps/api/src/kawach/llm/client.py`: Read via `os.getenv("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", "")`.
- **Existing Rate Limit & Throttling Logic:**
  - `groq_handler.py` contains `GroqRateLimiter` with:
    - `min_interval`: 2.0s anti-burst pacing sleep between calls.
    - Proactive sliding window: RPM limit (30) and TPM limit (6000), which forces `time.sleep(rpm_wait)` or `time.sleep(tpm_wait)`.
    - Token budgeting (`get_budgeted_max_tokens`).
    - Reactive 429 recovery: `time.sleep(wait_s)` where `wait_s` is read from `retry-after` or "try again in Xs", plus jitter.
  - `client.py` contains fallback retries:
    - Sleeps up to 45 seconds (`wait_seconds = [6.0, 12.0, 20.0, 30.0, 45.0]`) on 429.
  - `script_writer/agent.py`:
    - Hardcoded `time.sleep(1.2)` after every generated script to prevent TPM exhaustion on a single key.

#### 3. Agent Execution & Concurrency Model
- Backend pipelines run within the single FastAPI server process.
- Background runs (`_bg_explore_plan`, `_bg_execute`) are spawned as daemon threads via `threading.Thread(...)`.
- Test execution and verification parallelization runs via `concurrent.futures.ThreadPoolExecutor(max_workers=parallel_workers)`.
- Playwright browsers run as external child processes via `subprocess.run` / `Popen`.
- **Concurrency Decision for KeyPool:**
  - In-process concurrency is multi-threaded. Therefore, key rotation index, cooldown timestamps, and call counters require thread-safe synchronization (`threading.Lock`).
  - To support multi-worker server deployments (e.g., Uvicorn `--workers N`), the state can be augmented with a fast cross-process lock file or SQLite shared table, while maintaining fast in-memory atomicity protected by `threading.Lock` and file-backed / SQLite state synchronization.
  - We will implement `threading.Lock` for the atomic in-memory round-robin counter, with an optional SQLite/file-based sync layer for cross-process consistency if multiple worker processes are configured.

### Phase 1B & 1C: Implementation Details
- **Configuration Resolution (`kawach.core.config.Settings.get_groq_api_keys`)**:
  - Priority 1: `GROQ_API_KEYS` (comma-separated string).
  - Priority 2: `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`, ... (discovered via regex, sorted numerically).
  - Priority 3: `GROQ_API_KEY` (legacy single key fallback).
  - Whitespace trimmed, empty entries removed, identical keys de-duplicated preserving order.
  - Startup logger: `LLM key pool ready: N keys` (raw keys are NEVER logged or printed).
- **KeyPool Architecture (`apps/api/src/kawach/llm/key_pool.py`)**:
  - `KeyEntry`: Tracks `key` (raw secret), `masked_id` (`key#k ...last4`), `cooldown_until`, `disabled`, `consecutive_failures`, `requests`, `rate_limits_429`, `remaining_tokens`, `remaining_requests`.
  - Atomic selection: In-memory `threading.Lock()` controls selection and advances the rotation counter on every request, ensuring strict round-robin rotation (`K1 -> K2 -> K3 -> K1`).
  - Immediate 429 Rollover: On HTTP 429 / quota error, the key's cooldown is set based on `Retry-After`, `x-ratelimit-reset-*`, or error text (default 25s, cap 300s; or >= 600s for daily limits). The request is immediately retried on the next available key without sleeping while healthy keys exist.
  - Bounded Cooling Wait: When all keys are cooling down, the caller sleeps until the earliest cooldown expires with randomized jitter (max 6 passes, 120s wait cap). Exceeding limits raises `LLMRateLimitError`.
  - Auth Disabling (401/403): Key marked disabled for the process lifetime; logged with masked ID; execution continues with remaining keys.
  - Central Wrapper Function (`complete_with_pool`): All backend LLM calls route through this single function. No code outside `key_pool.py` directly calls `api.groq.com`.
  - Monitoring Endpoint: Protected route `GET /api/v1/llm/pool-status` returns operational telemetry with masked IDs only.

### Phase 1D: Verification & Live Test Results
- **Unit Test Suite (`apps/api/tests/test_key_pool.py`)**:
  - 13 passed in 0.82s:
    1. `test_strict_rotation_order_over_six_calls` -> Passed (Sequence: `[k1, k2, k3, k1, k2, k3]`).
    2. `test_immediate_rollover_on_429_without_sleep` -> Passed (Call 2 rollover to K3 with 0.0s sleep).
    3. `test_all_keys_429_waits_for_earliest_cooldown` -> Passed (Bounded sleep until earliest key ready).
    4. `test_permanent_429_raises_llm_rate_limit_error` -> Passed (`LLMRateLimitError` raised).
    5. `test_daily_limit_sets_long_cooldown` -> Passed (Cooldown >= 600s).
    6. `test_401_disables_key_and_continues_with_others` -> Passed (K1 disabled, K2 continues).
    7. `test_all_keys_disabled_raises_clear_error` -> Passed (Clear error raised).
    8. `test_header_duration_parsing` -> Passed (Handles `250ms`, `1m30s`, `2m`, `1.5s`, `30`, `60s`).
    9. `test_concurrency_parallel_distribution` -> Passed (60 parallel threads distribute exactly 20 calls to each of 3 keys).
    10. `test_keys_never_appear_in_logs_metrics_or_status` -> Passed (Secrets never present in logs or status responses).
    11. `test_single_key_legacy_mode` -> Passed (Single key operates seamlessly as pool of one).
    12. `test_grep_no_direct_groq_api_outside_wrapper` -> Passed (Zero direct Groq calls outside `key_pool.py`).
    13. `test_pool_status_api_endpoint` -> Passed (401 on unauth, 200 with masked telemetry on auth).
- **Live Groq API Test (3 configured keys)**:
  - Key 1 (`key#1 ...sCVi`): Answered HTTP 200 OK
  - Key 2 (`key#2 ...eJ3u`): Answered HTTP 200 OK
  - Key 3 (`key#3 ...KHxW`): Answered HTTP 200 OK
  - 4 consecutive round-robin calls across the live pool completed in 1.24s with distribution:
    `[('key#1 ...sCVi', 2), ('key#2 ...eJ3u', 1), ('key#3 ...KHxW', 1)]`

---

## PROBLEM 2: FINAL REPORT IS NOT GENERATED PROPERLY -> RELIABLE MD + PDF REPORT

### Phase 2A: Diagnosis & Evidence

#### 1. Report Generation Code Locations & Run Files
- **Orchestration**:
  - `apps/api/src/kawach/workflows/execute.py` (`node_build_report`): Calls `build_metrics(run_id)` and `build_report(run_id)`.
  - `apps/api/src/kawach/services/report_service.py`: Thin facade forwarding to `kawach.execution.reporting`.
  - `apps/api/src/kawach/execution/reporting.py`: The single location where `build_metrics` and `build_report` are implemented.
  - `apps/api/src/kawach/api/v1/reports.py`: Exposes `/runs/{id}/report`, `/runs/{id}/results`, `/runs/{id}/metrics`.
  - `apps/api/src/kawach/api/v1/exports.py`: Exports zips (`/runs/{id}/export`, `/runs/{id}/report/export`).
- **Run Artifacts Read**:
  - `run.json`, `input.json`, `catalog.json`, `results.json`, `bugs.json`, `app_map.json`, `review_log.json`, `llm_usage.json`, `parallel.json`, `blocked_requests.jsonl`, `evidence/`, `scripts/`, `verification/`, `repro/`.

#### 2. Root Causes Identified with Concrete Evidence from Finished Runs (`20261024-195639-82ad` & `20261024-195152-3688`)
- **Root Cause 1: PDF and HTML generation are completely non-existent.**
  - *Evidence*: `runs/20261024-195639-82ad/` and `runs/20261024-195152-3688/` contain only `report.md`. Neither `report.pdf` nor `report.html` was generated. The codebase had zero PDF rendering logic and no endpoints to serve or download a PDF.
- **Root Cause 2: Spec coverage matrix in `report.md` is completely empty.**
  - *Evidence*: In `runs/20261024-195639-82ad/report.md`, lines 118-120:
    ```markdown
    ## Coverage
    | Spec ID | Requirement | Tests | Result |
    | --- | --- | --- | --- |
    ```
    with zero rows underneath, and line 9: `Specification requirements covered: 6 of 0 items`.
    *Why*: `input.json` had `"spec": []` (empty list) because the user entered unstructured raw text (`specRaw`), and the planner generated tests with `specRef: ["S1", "S2", ...]` without storing normalized `SpecItem`s in `input.json`. `reporting.py` blindly iterated over `run_input.spec`, generating zero table rows.
- **Root Cause 3: Verification replay data (3 trials) and reproduction scripts are ignored.**
  - *Evidence*: Each run has full verification data in `verification/B01.json`, `verification/B02.json`, etc. (recording attempt numbers 1-3, `outcome: assertion_failure`, duration, and error message) and standalone reproduction Playwright scripts in `repro/B01_repro.spec.ts`.
  - However, `reporting.py` only output a single line: `- **Replay:** reproduced 3 of 3.`, omitting the 3-trial verification matrix and failing to embed the repro scripts.
  - Furthermore, there was no validation for missing or fake/placeholder replay data to flag defects as `UNVERIFIED`.
- **Root Cause 4: Test catalog is reduced to a flat 5-column table instead of complete per-test blocks.**
  - *Evidence*: `report.md` rendered only a brief Markdown table (`ID | Title | Spec Items | Outcome | Duration (s)`). It completely omitted per-test details: priority, category, page path, review decision and reason, numbered test steps (how it was tested), expected vs actual results, failure error messages, screenshots, and Playwright test script snippets. Rejected tests were omitted rather than highlighted in their own section.
- **Root Cause 5: Missing mandatory report sections.**
  - *Evidence*: The existing generator lacked:
    - Dedicated Cover Block (Title, Run ID, Project, Target URL, Date, Mode, Duration, Generated-by).
    - Scope and Method (how exploration, planning, review gate, Playwright scripting, execution, and 3x replays operated; budgets and masked credentials).
    - Results at a Glance matrix.
    - Application Map summary (pages, features, forms, and pages table).
    - Comprehensive Review Gate audit log (with human/auto reviewer, timestamp, and rejection/approval reasons).
    - Appendix (environment, versions, budgets hit, status glossary).
- **Root Cause 6: Missing `report_status` lifecycle tracking.**
  - *Evidence*: The `Run` schema and DB models lacked `report_status` (`pending`, `generating`, `ready`, `failed`) and `report_error`. If report generation threw an exception, it either crashed the pipeline or was lost without structured reporting status.
- **Root Cause 7: Missing download and regenerate endpoints.**
  - *Evidence*: No endpoints existed for `GET /api/v1/runs/{id}/report.pdf`, `GET /api/v1/runs/{id}/report.md`, or `POST /api/v1/runs/{id}/report/regenerate`. Frontend export buttons linked to `/report/export` which returned passing test scripts instead of the report itself.

### Phase 2B: New Architecture & Design (Deterministic First, LLM Optional)
- **Deterministic Assembly (`apps/api/src/kawach/execution/report_generator.py`)**:
  - Synthesizes report strictly from structured run artifacts (`run.json`, `input.json`, `catalog.json`, `results.json`, `bugs.json`, `app_map.json`, `review_log.json`, `llm_usage.json`, `metrics.json`, `verification/*.json`, `repro/*.spec.ts`, `scripts/*.spec.ts`, and `evidence/*`).
  - Implements a deterministic executive summary based on the headline numbers and verified defect counts. If an LLM call is used, strict token and timeout limits apply; if the LLM is down or times out, the deterministic synthesis is used seamlessly.
  - Exception containment: All report generation errors are trapped, logged with full traceback, and recorded in `run.report_status = "failed"` with `run.report_error`. Report errors never fail the test run itself.
- **Complete 11 Required Sections**:
  1. *Cover Block*: Title, Run ID, Project, Target URL, Date/Time, Mode, Wall Clock Duration, Platform attribution.
  2. *Executive Summary*: 5-8 lines, headline numbers, verified verdict (confirmed/flaky/not reproduced), and top risks.
  3. *Results at a Glance*: Summary table of planned, approved, executed, passed, failed, errored, flaky, not run, pass rate %, and spec coverage %.
  4. *Scope and Method*: How exploration, planning, review gate, Playwright scripting, execution, and 3-trial verification worked; pipeline budgets and masked credentials.
  5. *Spec Coverage Matrix*: Maps every spec requirement to its covering tests and coverage status (`Covered & Passed`, `Defect Confirmed`, `Flaky Finding`, `Not Covered`); lists uncovered spec items.
  6. *Test Case Catalog*: Every test rendered as its own complete block (ID, Title, Priority, Category, Spec Ref, Page/Path, Review decision & reason, Numbered steps, Expected result, Actual result, Outcome badge, Duration, Error message, Screenshot, Playwright TypeScript excerpt); separate table for tests rejected at the review gate with rejection reasons.
  7. *Defect Report & 3-Trial Verification*: Confirmed defects (3/3 reproductions only), Flaky defects (1-2/3 reproductions), Not Reproduced defects (0/3 reproductions), and Unverified candidates (for missing or placeholder replay data); complete 3-trial verification matrix (Trial, Outcome, Failure Type, Duration) and full Playwright reproduction scripts.
  8. *Application Map Topology*: Discovered pages, paths, forms, interactive element counts, and routes table.
  9. *Review Gate Audit Trail*: Log of review decisions, timestamps, actors, and reasons.
  10. *Execution & Cost*: Parallel workers, wall clock, stage timings table, LLM calls, input/output tokens, cost, and round-robin key pool statistics (requests, 429s, wait time per key).
  11. *Appendix*: Runtime environment versions (Python, Node.js, Playwright, OS), budgets hit, and status glossary.
- **Dual-Engine PDF Generation**:
  - Primary Engine: Playwright Chromium (`apps/api/scripts/render_pdf.cjs`). Renders high-fidelity `report.html` to A4 PDF with print stylesheets, repeating table headers, page breaks, and headers/footers with page numbers.
  - Fallback Engine: ReportLab (`_render_pdf_reportlab`). Built-in pure-Python fallback activated if Node/Playwright is unavailable.
  - Image handling: Embedded if file exists and <= 800 KB (max 40 images); otherwise formatted as link with size note. Missing images never break rendering.

### Phase 2C: Endpoints, Storage & Frontend
- **Endpoints (`apps/api/src/kawach/api/v1/reports.py`)**:
  - `GET /api/v1/runs/{id}/report.pdf`: Streams `application/pdf` with `Content-Disposition: attachment; filename="kawach-report-{id}.pdf"`. User-scoped (404 on foreign run).
  - `GET /api/v1/runs/{id}/report.md`: Returns `text/markdown`. User-scoped (404 on foreign run).
  - `POST /api/v1/runs/{id}/report/regenerate`: Triggers immediate deterministic regeneration of Markdown, HTML, and PDF from existing stored artifacts, updating `report_status`. User-scoped (404 on foreign run).
- **Export Bundle (`apps/api/src/kawach/services/export_service.py`)**:
  - Bundles `report.md`, `report.html`, and `report.pdf` into ZIP exports.
- **Frontend Integration (`apps/web`)**:
  - Updated `apps/web/src/features/reports/components/ReportView.tsx` and `ResultsView.tsx`: Added "Download PDF", "Download Markdown", and "Regenerate Report" buttons with status badges.
  - Updated API configs and TypeScript schemas (`ReportSchema` includes `report_status`, `report_error`, `has_pdf`, `has_md`).

### Phase 2D: Verification & Real Runs
- **Unit Test Suite (`apps/api/tests/test_report_generator.py`)**:
  - 8 passed in 11.53s:
    1. `test_normal_run_full_lifecycle` -> Passed (All 11 sections, 2 confirmed bugs, 1 flaky, 1 not reproduced, rejected tests, valid 13-page PDF).
    2. `test_zero_bugs_run` -> Passed (Zero bugs section, verified counts).
    3. `test_failed_or_cancelled_partial_run` -> Passed (Graceful generation with partial data).
    4. `test_missing_screenshots_graceful_handling` -> Passed (Missing images handled with note, no crashes).
    5. `test_special_characters_pipes_and_long_text` -> Passed (Pipes, quotes, emojis escaped; long text truncated cleanly).
    6. `test_large_scale_150_tests_performance` -> Passed (150 tests generated in < 1.0s).
    7. `test_missing_or_placeholder_verification_data_shows_unverified` -> Passed (Flagged as UNVERIFIED, excluded from confirmed).
    8. `test_api_report_endpoints_pdf_markdown_regenerate` -> Passed (Auth, regenerate, PDF download, MD download, 404 user isolation).
- **Combined Test Suite**:
  - 36 passed in 12.79s (`test_key_pool.py`, `test_groq_rate_limiting.py`, `test_report.py`, `test_report_generator.py`).
- **Frontend Build**:
  - `npm.cmd run build` passed with zero errors; all TypeScript checks and static page routes compiled.
- **Regeneration on Real Finished Runs**:
  - Run `20261024-195639-82ad`: `report.md` (29,771 bytes), `report.pdf` (267,130 bytes, 13 pages, Playwright Chromium).
  - Run `20261024-195152-3688`: `report.md` (30,211 bytes), `report.pdf` (271,408 bytes, 13 pages, Playwright Chromium).




