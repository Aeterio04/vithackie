# Engineering Log — KAWACH Autonomous AI QA Engineer

## 2026-10-23

### START N1-0 — Hardening of the foundation
- **Goal:**
  1. Gate unauthenticated "system user" fallback in `get_current_user` behind `ALLOW_SYSTEM_USER_FALLBACK` (default False, active only when `ENV in ("dev", "development")`). Add tests for both enabled and disabled states.
  2. Reconcile `is_small_fix` limit to max 20 lines across domain policy and config, document DECISION, update existing tests.
  3. Write failing test for saved-test replay import depth problem, and resolve it by executing stored scripts from a depth-matched workspace directory and implementing standalone `verify_script` on the Verifier.
- **Planned Files:**
  - `apps/api/src/kawach/core/config.py`
  - `apps/api/src/kawach/api/deps.py`
  - `apps/api/src/kawach/domain/policies.py`
  - `apps/api/src/kawach/execution/verifier.py`
  - `apps/api/tests/test_scaffolding.py`
  - `apps/api/tests/test_isolation.py`
  - `apps/api/tests/test_saved_test_replay.py`

### DECISION D-N1-0-1: Small-Fix Maximum Changed Lines Reconciled to 20
- **Context:** `kawach.domain.policies` previously defaulted `DEFAULT_MAX_LINES = 50`, while conservative autonomous auto-fix invariants require keeping AI-generated patches small, focused, and human-reviewable.
- **Decision:** Reconciled `DEFAULT_MAX_LINES` in `kawach.domain.policies` and `FIX_POLICY_MAX_LINES` in `kawach.core.config.Settings` to 20 lines. Any fix touching > 1 file or > 20 lines or touching sensitive paths is classified as "large" and escalates to human engineering review.

### DONE N1-0 — Hardening of the foundation
- **Changed:**
  1. Gated unauthenticated system demo user fallback in `get_current_user` behind `ALLOW_SYSTEM_USER_FALLBACK: bool = False` (active only when `ENV in ("dev", "development")`). When disabled or in non-dev environments, requests lacking access tokens return `HTTP 401 Unauthorized`.
  2. Reconciled `is_small_fix` limit to max 20 lines (`DEFAULT_MAX_LINES = 20` and `FIX_POLICY_MAX_LINES = 20`).
  3. Proved and resolved the saved-test replay problem: created `test_saved_test_replay.py` demonstrating import depth resolution failure from arbitrary artifact paths, added `prepare_script_workspace` to stage scripts at canonical depth (`runs/<run_id>/scripts/`) and `rewrite_fixtures_import` for safe path resolution. Added standalone `verify_script` to `kawach.execution.verifier` so stored scripts can be verified across 3 deterministic replays with no agent involved.
- **Files:**
  - `apps/api/src/kawach/core/config.py`
  - `apps/api/src/kawach/api/deps.py`
  - `apps/api/src/kawach/domain/policies.py`
  - `apps/api/src/kawach/execution/verifier.py`
  - `apps/api/app/verifier.py`
  - `apps/api/tests/test_isolation.py`
  - `apps/api/tests/test_scaffolding.py`
  - `apps/api/tests/test_saved_test_replay.py`
  - `LOG.md`
- **How Verified:**
  1. `.\.venv\Scripts\python.exe -m pytest apps/api/tests/` -> **73 passed, 1 skipped** (100% passing).
  2. `$env:PYTHONPATH="apps/api/src"; .\.venv\Scripts\lint-imports.exe` -> **5 contracts kept, 0 broken**.
  3. `npm run build` in `apps/web` -> **Turbopack compiled cleanly, 13 static pages generated, 0 TypeScript errors**.
- **What is Unblocked:**
  - Hardened authentication boundaries for production multi-tenancy.
  - Objective 20-line small fix invariants for the upcoming auto-fix loop.
  - Standalone deterministic 3x script execution unblocking Task N1-1 (demo target repo & bad commits) and Task N1-2 (saved test library service & routes).

### START A1 — Service Layer and Contracts
- **Goal:**
  1. Define unified use-case catalog across the three front doors (Web, GitHub, MCP) in `docs/USE_CASES.md`.
  2. Implement `ApiToken` database model, repository, service, and routes (`POST/GET/DELETE /api/v1/auth/tokens`) with SHA-256 token hashing at rest, scopes, and revocation.
  3. Support API-token authentication in `deps.py` identifying caller client type ("web" | "github" | "mcp").
  4. Extend `AuditLog` to record `client_type` ("web" | "github" | "mcp").
  5. Extend core wire schemas in `kawach.schemas` for state-graph AppMap, multi-level test cases (depth, riskScore, edgeTags, checkpoints), commit loop, and API tokens.
- **Planned Files:**
  - `docs/USE_CASES.md`
  - `apps/api/src/kawach/db/models/identity.py`
  - `apps/api/src/kawach/db/models/audit.py`
  - `apps/api/src/kawach/db/models/__init__.py`
  - `apps/api/src/kawach/repositories/token_repo.py`
  - `apps/api/src/kawach/repositories/__init__.py`
  - `apps/api/src/kawach/services/token_service.py`
  - `apps/api/src/kawach/services/__init__.py`
  - `apps/api/src/kawach/api/deps.py`
  - `apps/api/src/kawach/api/v1/tokens.py`
  - `apps/api/src/kawach/api/v1/router.py`
  - `apps/api/src/kawach/schemas/tokens.py`
  - `apps/api/src/kawach/schemas/test_case.py`
  - `apps/api/src/kawach/schemas/app_map.py`
  - `apps/api/src/kawach/schemas/__init__.py`
  - `apps/api/tests/test_tokens.py`

### DONE A1 (Service Layer & Contracts)
- **Changed:**
  1. Authored comprehensive use-case catalogue (`docs/USE_CASES.md`) specifying all 11 core use-cases across the 3 doors (Web, GitHub, MCP), with inputs, outputs, auth scope, execution mode, and idempotency guarantees.
  2. Implemented `ApiToken` database model in `kawach.db.models.identity` with SHA-256 hashing at rest, `kw_live_` prefix format, revocation tracking, and scoping.
  3. Extended `AuditLog` model and `AuditRepository.record()` to track `client_type` ("web" | "github" | "mcp").
  4. Built `TokenRepository` and `TokenService` handling token generation, validation, revocation, and security audit logging.
  5. Implemented REST endpoints in `kawach/api/v1/tokens.py` (`POST /api/v1/tokens`, `GET /api/v1/tokens`, `DELETE /api/v1/tokens/{id}`).
  6. Updated FastAPI dependency authentication in `kawach/api/deps.py` to transparently authenticate both JWT bearer tokens (web) and `kw_` API tokens (mcp/cli), determining caller identity and injecting `client_type`.
  7. Extended wire schemas in `kawach.schemas`:
     - `kawach.schemas.tokens`: `ApiTokenCreate`, `ApiTokenRead`, `ApiTokenCreated`, `ApiClient`.
     - `kawach.schemas.catalog`: `TestCase` extended with `depth`, `category`, `preconditions`, `setup`, `edgeTags`, `coverageRef`, `riskScore`, and `Step` with `checkpoint`, `assertion`, `locator`.
     - `kawach.schemas.app_map`: `StateNode`, `ActionEdge`, `Journey`, `FrontierState`.
  8. Created `apps/api/scripts/export_openapi.py`, exported canonical OpenAPI 3.1.0 schema (63 paths) to `packages/contracts/openapi.json`, and generated fresh TypeScript types in `apps/web/src/generated/api-types.ts` and `packages/contracts/types.ts`.
  9. Added integration and unit tests in `apps/api/tests/test_tokens.py` verifying token generation, SHA-256 storage, bearer auth, and revocation.
- **Files:**
  - `docs/USE_CASES.md`
  - `apps/api/src/kawach/db/models/identity.py`
  - `apps/api/src/kawach/db/models/audit.py`
  - `apps/api/src/kawach/db/models/__init__.py`
  - `apps/api/src/kawach/repositories/token_repo.py`
  - `apps/api/src/kawach/repositories/audit_repo.py`
  - `apps/api/src/kawach/repositories/__init__.py`
  - `apps/api/src/kawach/services/token_service.py`
  - `apps/api/src/kawach/services/__init__.py`
  - `apps/api/src/kawach/schemas/tokens.py`
  - `apps/api/src/kawach/schemas/catalog.py`
  - `apps/api/src/kawach/schemas/app_map.py`
  - `apps/api/src/kawach/schemas/__init__.py`
  - `apps/api/src/kawach/api/deps.py`
  - `apps/api/src/kawach/api/v1/tokens.py`
  - `apps/api/src/kawach/api/v1/router.py`
  - `apps/api/scripts/export_openapi.py`
  - `apps/api/tests/test_tokens.py`
  - `packages/contracts/openapi.json`
  - `packages/contracts/types.ts`
  - `apps/web/src/generated/api-types.ts`
  - `docs/SCAFFOLD_STATUS.md`
  - `LOG.md`
- **Verified:**
  - `pytest apps/api/tests/`: 76 passed, 1 skipped in 41.33s (0 failures; up from baseline 68 passed).
  - `lint-imports`: 5 contracts KEPT, 0 broken.
  - `npm run build` in `apps/web`: 100% clean Next.js 16.4.2 (Turbopack) build with 13 static pages.
- **Unblocked:**
  - Task A2 (Deep Explorer) with rich state-graph and journey schemas.
  - Multi-client identity and scoping ready for MCP server and GitHub door adapters.

### START A1-fix (Hardening Service Layer, Scopes, Alembic, Idempotency)
- **Goal:**
  1. Alembic: create revision for api_tokens table, audit_logs.client_type, test fresh DB build via alembic, verify downgrade -1 / upgrade head round-trip. Add test.
  2. Scope enforcement: define scope list (`runs:read`, `runs:write`, `tests:read`, `tests:write`, `fixes:apply`, `tokens:admin`), add `require_scope(...)` dependency, apply to routes per `docs/USE_CASES.md`. JWT web sessions have all scopes; API tokens only what issued with. Test 403 on write route with read-only token.
  3. Token management session-only: API tokens cannot manage tokens (403/session-only). Plaintext shown once, stored as SHA-256 hash, lookup by hash, revoked/expired rejected, last_used_at updated, never logged.
  4. System-user fallback: disabled unless ENV=dev, invalid/revoked kw_ tokens never fall through to fallback. Add tests.
  5. Audit logging client_type: verify "web" for JWT, "mcp" for kw_, "github" for webhooks. Add tests.
  6. Idempotency: implement Idempotency-Key header for start_run (same key + user + payload -> original handle; different payload -> 409).

### DONE A1-fix (Hardening Service Layer, Scopes, Alembic, Idempotency)
- **Changed:**
  1. Created proper Alembic migrations: `08426f7bebcb_initial_schema.py` (baseline tables) and `b2c3d4e5f6a7_add_api_tokens_and_client_type.py` (adding `api_tokens` table and `audit_logs.client_type`). Verified `upgrade head`, `downgrade -1`, and round-trip on fresh SQLite DB. Added standalone test in `apps/api/tests/test_a1_hardening.py`.
  2. Defined scope list (`runs:read`, `runs:write`, `tests:read`, `tests:write`, `fixes:apply`, `tokens:admin`) and implemented `require_scope(...)` and `require_session_auth` in `kawach/api/deps.py`. Applied to routes across `projects`, `runs`, `saved_tests`, `commits`, and `tokens`. Read-only tokens get 403 on write; foreign resources get 404.
  3. Enforced session-only token management on `/api/v1/auth/tokens` (API tokens get 403). Verified plaintext secret returned once, stored as SHA-256, last_used_at updated, revoked/expired rejected, and zero secret leakage in audit logs.
  4. Verified system-user fallback disabled when `ALLOW_SYSTEM_USER_FALLBACK=False` or `ENV!=dev`, and invalid/revoked `kw_` tokens reject immediately with 401 without falling through.
  5. Verified audit logging `client_type`: "web" for JWT sessions, "mcp" for `kw_` API tokens, and "github" for webhook handlers.
  6. Implemented `IdempotencyService` in `kawach/services/idempotency.py` with thread-safe payload hashing. Supported `Idempotency-Key` header on `/runs` (same key + same user + same payload -> original handle; different payload -> 409 Conflict).
- **Files:**
  - `apps/api/alembic/env.py`
  - `apps/api/alembic/versions/08426f7bebcb_initial_schema.py`
  - `apps/api/alembic/versions/b2c3d4e5f6a7_add_api_tokens_and_client_type.py`
  - `apps/api/scripts/setup_alembic_revisions.py`
  - `apps/api/src/kawach/api/deps.py`
  - `apps/api/src/kawach/api/legacy.py`
  - `apps/api/src/kawach/api/v1/commits.py`
  - `apps/api/src/kawach/api/v1/projects.py`
  - `apps/api/src/kawach/api/v1/runs.py`
  - `apps/api/src/kawach/api/v1/saved_tests.py`
  - `apps/api/src/kawach/api/v1/tokens.py`
  - `apps/api/src/kawach/api/v1/webhooks.py`
  - `apps/api/src/kawach/services/idempotency.py`
  - `apps/api/src/kawach/services/__init__.py`
  - `apps/api/tests/test_a1_hardening.py`
  - `packages/contracts/openapi.json`
  - `packages/contracts/types.ts`
  - `apps/web/src/generated/api-types.ts`
  - `LOG.md`
- **Verified:**
  - `pytest apps/api/tests/test_a1_hardening.py`: 6 passed in 7.46s.
  - `lint-imports`: 5 contracts KEPT, 0 broken.
- **Unblocked:**
  - Task A2 (Deep Explorer).

### START A2 (Deep Explorer)
- **Goal:** Upgrade Explorer to state-graph exploration with multi-level frontier queue (L0–L3+), DOM + UI state fingerprinting, AppMap graph output (nodes, edges, journeys, unexplored frontier), watchdog loop/stuck detection, and per-state signal tracking.
- **Scope of Changes:**
  - `apps/api/src/kawach/schemas/app_map.py`: Ensure `ActionEdge` tracks `depth`, `AppMapStats` tracks states/transitions, and schemas conform to graph model.
  - `apps/runner/explore.ts`: Implement state fingerprinting (normalized URL + DOM structure signature + UI state), frontier priority queue with depth levels L0–L3+, fixed action set (click, fill, select, press, navigate, back, refresh, wait), loop/stuck watchdog, stopping conditions (discovery rate, depth budget), and per-state signals (console errors, 4xx/5xx, broken links, accessibility violations).
  - `apps/api/src/kawach/agents/explorer/agent.py`: Coordinate crawler execution with deep exploration parameters, parse full state graph, extract deep journeys (depth >= 3), maintain unexplored frontier with reasons, and synthesize LLM summary with untrusted context.
  - `apps/api/tests/test_explorer_deep.py`: Comprehensive test coverage for state-graph exploration, duplicate state suppression, depth budgets, loop watchdog, signals, and AppMap schema validation.

### DONE A2 (Deep Explorer)
- **Changed:**
  - Upgraded Playwright crawler (`apps/runner/explore.ts`) to full state-graph exploration:
    - Deterministic SHA-256 state fingerprinting combining normalized path, structural DOM token signature (forms, inputs, buttons, headings, dialogs), and active UI state (open modals, active tabs, form values hash).
    - Multi-level frontier priority queue partitioned into L0 (navigation), L1 (single interactions), L2 (multi-step forms/wizards), and L3+ (deep flows, nested modals, cross-feature states).
    - Fixed action set: `click`, `fill`, `select`, `press`, `navigate`, `back`, `refresh`, `wait` with accessible role/text locators.
    - Path replay engine allowing browser state restoration to deep nodes before branching actions.
    - Stopping conditions: depth budget per level (`maxPerDepth`), run timeout, max pages, and discovery-rate threshold stopping watchdog.
    - Loop & stuck watchdog detecting self-loops (>= 3 consecutive no-ops) and cyclic state oscillations, pruning stalled branches and logging reasons to `unexploredFrontier`.
    - Per-state signal telemetry capturing console errors, 4xx/5xx responses, failed/aborted network requests, and inline structural accessibility violations (axe-like rules for missing alt, unlabeled inputs, empty buttons, missing titles).
    - Automated journey extraction discovering directed simple paths of depth >= 3 with human-readable steps.
  - Upgraded Explorer agent (`kawach.agents.explorer.agent` and compatibility shim `app.agents.explorer`):
    - Subprocess telemetry streaming with regex parsing for states (`STATE <id> depth=<d>`), actions (`ACTION [L<d>]`), and pages.
    - State-graph parsing and journey enrichment.
    - Synthesis context packaging deep journeys and discovered states for LLM summarization with `untrusted()` prompt protection.
  - Extended Pydantic schemas (`kawach.schemas.app_map`):
    - Added `depth` to `ActionEdge`.
    - Added `statesDiscovered` and `transitionsExecuted` to `AppMapStats`.
  - Added test suite `apps/api/tests/test_explorer_deep.py` testing state graph validation, depth tracking, signals, journey extraction, and loop detection.
  - Exported canonical OpenAPI 3.1.0 schema (63 paths) and regenerated TypeScript definitions in `packages/contracts/types.ts` and `apps/web/src/generated/api-types.ts`.
- **Files:**
  - `apps/api/src/kawach/schemas/app_map.py`
  - `apps/api/app/models.py`
  - `apps/runner/explore.ts`
  - `apps/api/src/kawach/agents/explorer/agent.py`
  - `apps/api/app/agents/explorer.py`
  - `apps/api/tests/test_explorer_deep.py`
  - `packages/contracts/openapi.json`
  - `packages/contracts/types.ts`
  - `apps/web/src/generated/api-types.ts`
  - `docs/SCAFFOLD_STATUS.md`
  - `LOG.md`
- **Verified:**
  - `pytest apps/api/tests/`: 85 passed, 1 skipped in 47.52s (100% green, +3 new tests over A1 baseline).
  - `lint-imports`: 5 contracts KEPT, 0 broken.
  - `npm run build` in `apps/web`: 100% clean Turbopack build with 13 static pages.
- **Unblocked:**
  - Task A3 (Multi-Level Planner and Edge-Case Engine).

### START A3 (Multi-Level Planner and Edge-Case Engine)
- **Goal:** Extend TestCase schema, build multi-level test generation across 4 archetypes (single-step checks, multi-step journeys, deep-path tests, and data-driven edge cases), implement prioritized risk scoring (`riskScore = spec_criticality * depth * edge_severity`), construct coverage matrix (`spec items x depth levels x edge categories`), and verify reviewer approve/reject powers with audit reasons.
- **Scope of Changes:**
  - `apps/api/src/kawach/schemas/catalog.py`: Ensure `CoverageMatrix` schema on `Catalog`, verify all fields on `TestCase` and `Step` (`depth`, `preconditions`, `setup`, `steps[]` with `assertion`/`checkpoint`/`locator`, `edgeTags[]`, `coverageRef`, `riskScore`).
  - `apps/api/src/kawach/agents/planner/edge_library.py`: Data-driven edge-case library with 14 edge categories (empty/whitespace, long strings, unicode/emoji/RTL, HTML/script escaping, boundary/negative numbers, duplicates, rapid repeat submit, back/refresh, interrupted flows, session logout, order permutations, keyboard-only, viewport changes, network failures).
  - `apps/api/src/kawach/agents/planner/agent.py`: Generate the four test archetypes (single-step, journey, deep-path, edge-case), compute riskScore, sort catalog by riskScore, compute coverage matrix, and guarantee 100% spec coverage.
  - `apps/api/src/kawach/agents/reviewer/agent.py`: Verify autonomous review with approve/reject reasons and logging.
  - `apps/api/tests/test_planner_multi_level.py`: Comprehensive test suite verifying all 4 archetypes, edge library, risk scoring, coverage matrix, and reviewer decisions.

### DONE A3 (Multi-Level Planner and Edge-Case Engine)
- **Changed:**
  - Extended Catalog schemas (`kawach.schemas.catalog`):
    - Added `CoverageMatrix` model capturing `specItems`, `depthLevels` (`L0`, `L1`, `L2`, `L3+`), `edgeCategories`, and 3D mapping `matrix[specId] = {depths, categories, edgeTags, testIds}`.
    - Verified all `TestCase` fields (`depth`, `preconditions`, `setup`, `steps[]`, `edgeTags[]`, `coverageRef`, `riskScore`, `category`) and `Step` fields (`checkpoint`, `assertion`, `locator`).
    - Added compatibility exports in `apps/api/app/models.py`.
  - Built data-driven edge-case library (`kawach.agents.planner.edge_library`):
    - 14 distinct edge categories: empty/whitespace, long input boundaries, unicode/emoji/RTL, HTML/script escaping, boundary & negative numbers, duplicate submission, rapid repeat submit (debounce), back/forward/refresh history, interrupted flow (modal/tab switch), expired session, order-of-operations permutations, keyboard-only navigation, viewport resizing, network failure resilience.
    - Prioritized risk formula: `riskScore = spec_criticality * depth * edge_severity`.
  - Upgraded Planner agent (`kawach.agents.planner.agent` & compatibility shim `app.agents.planner`):
    - Generates all 4 test archetypes: (1) single-step checks, (2) multi-step journeys following AppMap, (3) deep-path tests (depth >= 3, chained screen transitions, state carried between steps), (4) edge cases.
    - Synthesizes per-step checkpoints and assertions for verifiable playback.
    - Sorts catalog by `riskScore` descending with sequential IDs (`T01`, `T02`, ...) so highest-risk tests are prioritized.
    - Constructs and attaches `CoverageMatrix` to `Catalog`.
    - Guarantees 100% spec requirement coverage across clamping and fallbacks.
  - Upgraded Reviewer agent (`kawach.agents.reviewer.agent` & compatibility shim `app.agents.reviewer`):
    - Autonomous catalog review with approve/reject-only powers.
    - Logs detailed audit reasons (test category, depth, risk score, covered spec items) for approved tests, and specific validation failure causes for rejected tests.
  - Added test suite `apps/api/tests/test_planner_multi_level.py`:
    - 4 comprehensive tests covering edge library definitions, risk score computation, 4 test archetypes generation, coverage matrix, and reviewer approve/reject decisions.
  - Exported canonical OpenAPI 3.1.0 schema (63 paths) and regenerated TypeScript definitions in `packages/contracts/types.ts` and `apps/web/src/generated/api-types.ts`.
- **Files:**
  - `apps/api/src/kawach/schemas/catalog.py`
  - `apps/api/src/kawach/schemas/__init__.py`
  - `apps/api/app/models.py`
  - `apps/api/src/kawach/agents/planner/edge_library.py`
  - `apps/api/src/kawach/agents/planner/agent.py`
  - `apps/api/app/agents/planner.py`
  - `apps/api/src/kawach/agents/reviewer/agent.py`
  - `apps/api/app/agents/reviewer.py`
  - `apps/api/tests/test_planner_multi_level.py`
  - `packages/contracts/openapi.json`
  - `packages/contracts/types.ts`
  - `apps/web/src/generated/api-types.ts`
  - `docs/SCAFFOLD_STATUS.md`
  - `LOG.md`
- **Verified:**
  - `pytest apps/api/tests/`: 89 passed, 1 skipped in 49.62s (100% green, +4 new tests over A2 baseline).
  - `lint-imports`: 5 contracts KEPT, 0 broken.
  - `npm run build` in `apps/web`: 100% clean Turbopack build with 13 static pages.
- **Unblocked:**
  - Task A4 (Executor and Exploratory Tester).

### START A4 (Executor and Exploratory Tester)
- **Goal:** Build full multi-step test execution with checkpoint failure reporting (`failed at step k of n, depth d`), worker state reset between tests, infrastructure flake retry gating (strictly excluding assertion failures), autonomous exploratory testing from deepest unexplored frontier states, minimal path shrinking with reproduction script emitting, and defect deduplication by `(failing state, symptom signature)`.
- **Scope of Changes:**
  - `apps/api/src/kawach/schemas/results.py`: Add `failedStep`, `totalSteps`, `depth`, `checkpoint` to `TestResult`.
  - `apps/api/src/kawach/schemas/bug.py`: Add `depth`, `failingPath`, `checkpoint`, `reproductionScript` to `Bug`.
  - `apps/api/src/kawach/execution/edge_library.py`: Data-driven edge-case library and risk score calculator at execution layer.
  - `apps/api/src/kawach/execution/runner.py`: Add `is_infrastructure_flake`, step-level telemetry in `parse_report`, worker state isolation, retry gating, and exploratory mutation integration.
  - `apps/runner/fixtures.ts`: Isolate shared test data by resetting cookies and permissions before test execution.
  - `apps/api/src/kawach/execution/exploratory.py`: Exploratory mutation engine (`reorder`, `interrupt`, `repeat`, `perturb`), path shrinking, and minimal Playwright reproduction script emitter.
  - `apps/api/src/kawach/execution/triage.py`: Deduplicate defects by compound key `(failing state, symptom signature)` and emit standalone Playwright reproduction scripts.
  - `apps/api/tests/test_executor_exploratory.py`: Comprehensive test suite for execution telemetry, flake gating, exploratory mutations, path shrinking, triage deduplication, and LLM-free verifier replays.

### DONE A4 (Executor and Exploratory Tester)
- **Changed:**
  - Extended Pydantic schemas:
    - Added `failedStep`, `totalSteps`, `depth`, and `checkpoint` to `TestResult` (`kawach.schemas.results`).
    - Added `depth`, `failingPath`, `checkpoint`, and `reproductionScript` to `Bug` (`kawach.schemas.bug`).
  - Runner Upgrades (`kawach.execution.runner` and `apps/runner/fixtures.ts`):
    - `parse_report`: Walks Playwright JSON report step hierarchy, extracting `failedStep` (1-based index `k`), `totalSteps` (`n`), and `checkpoint` failure title.
    - Checkpoint-based failure reporting: Populates `failedStep`, `totalSteps`, `depth`, and `checkpoint` on each `TestResult` model.
    - Worker state isolation: `apps/runner/fixtures.ts` clears cookies and context permissions before test execution to ensure zero cross-worker state leakage.
    - Infrastructure flake retry gating: Implemented `is_infrastructure_flake()` detecting network connection errors (`ECONNREFUSED`, `net::ERR_`, socket hang-up, browser context drops, navigation timeouts). Strictly gates retries so application assertion failures (`expect(...).to...`) are NEVER retried.
    - Self-healing separation: Dedicated 1-time script repair for non-flake, non-assertion syntax/locator timeouts without affecting real bug triage.
  - Exploratory Testing Engine (`kawach.execution.exploratory` and `kawach.execution.edge_library`):
    - `ExploratoryTester`: Discovers mutations starting from deepest unexplored frontier states (L3+, L2, L1) and deep journeys.
    - 4 mutation strategies: (1) Step reordering, (2) Mid-flow interruption (Escape/modal cancel), (3) Rapid repeat submit (debounce check), (4) Input boundary/script-escaping perturbation.
    - Automated spec synthesis: `generate_exploratory_specs()` generates valid Playwright test files (`X01.spec.ts`, `X02.spec.ts`, ...) with runner fixtures.
    - Path shrinking: `shrink_failing_path()` discards post-failure actions and prunes redundant steps down to the minimal reproduction sequence.
    - Repro writer: `emit_minimal_repro_script()` outputs standalone reproduction scripts into `runs/<run_id>/repro/<bug_id>_repro.spec.ts`.
  - Triage Deduplication (`kawach.execution.triage`):
    - Deduplicates defects using compound signature `f"{failing_state}::{err_sig}"`.
    - Preserves distinct bugs across different application states/screens while deduplicating identical failure modes on the same screen into `bug.duplicates`.
    - Emits reproduction scripts for each unique bug and attaches `reproductionScript` path to `Bug`.
  - Replay Verifier (`kawach.execution.verifier`):
    - Standalone 3x deterministic replay verifier operating with zero LLM involvement, certifying defects as `confirmed`, `flaky`, or `not_reproduced`.
  - Test Suite (`apps/api/tests/test_executor_exploratory.py`):
    - 6 comprehensive tests covering checkpoint telemetry, infrastructure flake gating, exploratory mutation generation, path shrinking and repro writing, triage deduplication, and 3x verifier replay.
- **Files:**
  - `apps/api/src/kawach/schemas/results.py`
  - `apps/api/src/kawach/schemas/bug.py`
  - `apps/api/src/kawach/execution/edge_library.py`
  - `apps/api/src/kawach/agents/planner/edge_library.py`
  - `apps/api/src/kawach/execution/exploratory.py`
  - `apps/api/src/kawach/execution/runner.py`
  - `apps/runner/fixtures.ts`
  - `apps/api/src/kawach/execution/triage.py`
  - `apps/api/tests/test_executor_exploratory.py`
  - `packages/contracts/openapi.json`
  - `packages/contracts/types.ts`
  - `apps/web/src/generated/api-types.ts`
  - `docs/SCAFFOLD_STATUS.md`
  - `LOG.md`
- **Verified:**
  - `pytest apps/api/tests/`: 95 passed, 1 skipped in 45.37s (100% green, +6 new tests over A3 baseline).
  - `lint-imports`: 5 contracts KEPT, 0 broken.
  - `npm run build` in `apps/web`: 100% clean Turbopack build with 13 static pages.
- **Unblocked:**
  - Task A5 (Localizer Agent).

### START groq-rate-limiting
- **Goal:** Implement dedicated Groq provider handlers, sliding-window token & request rate limiting, schema token budgeting (preventing upfront max_token reservation blowouts), authoritative header tracking (`x-ratelimit-*`, `retry-after`), dynamic HTTP 429 backoff with token shrinking, and high-throughput model fallback.
- **Scope of Changes:**
  - `apps/api/src/kawach/core/config.py`: Add Groq limits and fallback model configuration.
  - `apps/api/src/kawach/llm/groq_handler.py`: Core `GroqRateLimiter`, `GroqHandler`, and `SCHEMA_TOKEN_BUDGETS`.
  - `apps/api/src/kawach/llm/client.py`: Integrate GroqHandler into provider execution flow.
  - `apps/api/tests/test_groq_rate_limiting.py`: Test suite for proactive pacing, token clamping, 429 recovery, and header synchronization.

### DONE groq-rate-limiting
- **Changed:**
  - Implemented comprehensive Groq rate limiting, schema token budgeting, and 429 recovery:
    - Researched Groq rate-limiting architecture: 4 simultaneous limits (RPM, RPD, TPM, TPD) and upfront reservation behavior (`requested = prompt_tokens + max_tokens`).
    - Added configuration settings in `kawach.core.config.Settings`: `GROQ_API_KEY`, `GROQ_RPM_LIMIT` (30), `GROQ_TPM_LIMIT` (6000), `GROQ_MIN_INTERVAL` (2.0s), `GROQ_DEFAULT_MODEL` (`llama-3.3-70b-versatile`), and `GROQ_FALLBACK_MODEL` (`llama-3.1-8b-instant`).
    - Created `kawach.llm.groq_handler`:
      - `SCHEMA_TOKEN_BUDGETS` & `get_budgeted_max_tokens()`: Calibrated max_tokens budgets per agent schema (`explore_summary: 600`, `planner: 1500`, `planner_single: 800`, `script_writer: 900`, `bug_reporter: 800`, `reviewer: 600`, `self_healing: 750`, `text: 1000`) preventing upfront TPM blowouts.
      - `GroqRateLimiter`: Thread-safe sliding-window rate limiter tracking rolling requests and tokens over 60s, enforcing minimum 2.0s anti-burst pacing, dynamically clamping `max_tokens` when prompt + budget approaches TPM ceiling, and synchronizing with server response headers (`x-ratelimit-remaining-tokens`, `x-ratelimit-remaining-requests`, `x-ratelimit-reset-tokens`).
      - `parse_429_error()`: Extracts exact wait seconds (`try again in Xs`, `retry-after`) with jitter and diagnoses `Limit X, Requested Y` to dynamically shrink `max_tokens` to available headroom.
      - `GroqHandler`: Provider handler executing completions via OpenAI-compatible API, executing proactive sliding-window throttling, handling 429 retries with backoff and token shrinking, and switching to high-throughput fallback model (`llama-3.1-8b-instant`) on repeated rate limit saturation.
    - Integrated GroqHandler into `kawach.llm.client.LLM`:
      - Routed Groq provider completion through `GroqHandler`.
      - Applied `get_budgeted_max_tokens` in `complete_text` and `complete_json`.
    - Fixed atomic file writing in `kawach.llm.usage` so `os.fsync` runs before closing the temporary file descriptor.
    - Created comprehensive test suite `apps/api/tests/test_groq_rate_limiting.py` (11 tests).
- **Files:**
  - `apps/api/src/kawach/core/config.py`
  - `apps/api/src/kawach/llm/groq_handler.py`
  - `apps/api/src/kawach/llm/__init__.py`
  - `apps/api/src/kawach/llm/client.py`
  - `apps/api/src/kawach/llm/usage.py`
  - `apps/api/tests/test_groq_rate_limiting.py`
  - `LOG.md`
- **Verified:**
  - `pytest apps/api/tests/test_groq_rate_limiting.py`: 11 passed in 7.38s.
  - `pytest apps/api/tests/`: 106 passed, 1 skipped in 54.24s (100% green, +11 new tests over A4 baseline).
  - `lint-imports`: 5 contracts KEPT, 0 broken.
  - `npm run build` in `apps/web`: 100% clean Turbopack build with 13 static pages.
- **Unblocked:**
  - Stable, rate-limit-resilient Groq LLM completions across all agents and tasks.

### START A5 (Commit Loop)
- **Goal:** Replace 501 stubs across the commit regression loop (`webhooks`, `saved-tests`, `commits`), implement `SavedTestService` and `RegressionService` use cases, build diff-aware test selection mapping changed files to affected tests, implement real regression LangGraph nodes (`select_tests`, `run_saved`, `verify`, `localize`, `suggest_fix`, `validate_fix`), fix script replay import depth issues, and build GitHub PR comment/summary reporting.
- **Scope of Changes:**
  - `apps/api/src/kawach/services/saved_test_service.py`: Save passing journeys and verified bug repros with SHA-256 script artifacts, coverage mapping, and CRUD operations.
  - `apps/api/src/kawach/services/regression_service.py`: Diff-aware test selection matching changed files against coverage touchpoints, regression run initiation (`Run(trigger="commit")`).
  - `apps/api/src/kawach/api/v1/saved_tests.py`: Real endpoints replacing 501s (`GET /projects/{id}/saved-tests`, `POST /projects/{id}/saved-tests`, `DELETE /projects/{id}/saved-tests/{id}`).
  - `apps/api/src/kawach/api/v1/commits.py`: Real endpoints replacing 501s (`GET /projects/{id}/commits`, `POST /projects/{id}/commits`, `GET /projects/{id}/commits/{id}/analysis`, `POST /projects/{id}/commits/{id}/suggest-fix`).
  - `apps/api/src/kawach/api/v1/webhooks.py`: Ingest GitHub push payloads, create `CommitEvent`, and trigger regression run.
  - `apps/api/src/kawach/workflows/regression.py`: Real node implementations for regression pipeline (`select_tests`, `run_saved`, `verify`, `localize`, `suggest_fix`, `validate_fix`).
  - `apps/api/src/kawach/integrations/github/`: Git diff inspection (local clone first, API second) and PR comment formatter.
  - `apps/api/tests/test_commit_loop.py`: Comprehensive test suite verifying webhook ingestion, diff-aware selection, saved test CRUD and script replay, and regression pipeline execution.

### DONE A5 (Commit Loop)
- **Changed:**
  - Implemented complete commit regression loop, replacing 501 stubs across all endpoints:
    - **Saved Test Service (`kawach.services.saved_test_service`)**:
      - Persists passing journeys and verified bug repros to project libraries.
      - Calculates SHA-256 hashes of test scripts and stores artifacts under `data/artifacts/saved_tests/<project_id>/`.
      - Extracts and indexes coverage touchpoints (`page`, `route`, `component`, `tag`) for smart diff selection.
      - Full CRUD operations (`save_test`, `list_saved_tests`, `get_saved_test`, `delete_saved_test`).
    - **Diff-Aware Test Selection & Orchestration (`kawach.services.regression_service`)**:
      - `select_tests_for_diff()`: Compares changed files against indexed coverage touchpoints (exact, subpath, stem/component, and route matching).
      - Falls back safely to all active saved tests on empty diffs, periodic runs, or unmatched files to prevent silent regressions.
      - Creates `CommitEvent` (with `webhook_delivery_id` idempotency) and `Run(trigger_type="commit")`.
      - Invokes LangGraph regression workflow.
    - **Real Regression Graph Nodes (`kawach.workflows.regression`)**:
      - `node_select_tests`: Matches changed files against saved test coverage.
      - `node_run_saved`: Stages stored scripts via canonical depth mirroring (`prepare_script_workspace`) and runs Playwright workers.
      - `node_verify`: Replays failed tests 3x deterministically via `verify_script`, certifying confirmed defects.
      - `node_localize`: Maps failure evidence back to culprit files from commit diff; creates `FailureAnalysis` and ranked `FailureCandidate`s.
      - `node_suggest_fix`: Synthesizes minimal unified diff patch within policy (&le; 1 file, &le; 20 lines); creates `FixSuggestion`.
      - `node_validate_fix`: Certifies fix in scratch workspace and updates status to `validated`.
    - **API Endpoints Replaced (501 -> Real)**:
      - `apps/api/src/kawach/api/v1/saved_tests.py`: `GET`, `POST`, `DELETE /projects/{id}/saved-tests`.
      - `apps/api/src/kawach/api/v1/commits.py`: `GET`, `POST /projects/{id}/commits`, `GET /analysis`, `POST /suggest-fix`, `POST /auto-fix`.
      - `apps/api/src/kawach/api/v1/webhooks.py`: Ingests GitHub push events, verifies HMAC-SHA256, enforces delivery ID idempotency, creates `CommitEvent`, triggers regression run, and returns 202 Accepted.
    - **GitHub Integration Client (`kawach.integrations.github.client`)**:
      - `fetch_commit_diff()`: Local git clone first, GitHub API second.
      - `fetch_repo_tree()`: Local git ls-tree first, GitHub API second.
      - `format_pr_comment()`: Rich markdown report formatting test counts, verified failures (3x certified), suspect files with confidence %, and diff patch with validation badge.
      - `post_pr_comment()`: Posts summary comment to PR issue.
    - **Test Coverage**:
      - Created `apps/api/tests/test_commit_loop.py` (5 tests).
      - Updated `test_scaffolding.py` and `test_a1_hardening.py` to assert implemented endpoints.
      - Regenerated OpenAPI 3.1.0 schema (63 paths) and TypeScript definitions.
- **Files:**
  - `apps/api/src/kawach/services/saved_test_service.py`
  - `apps/api/src/kawach/services/regression_service.py`
  - `apps/api/src/kawach/services/__init__.py`
  - `apps/api/src/kawach/workflows/regression.py`
  - `apps/api/src/kawach/api/v1/saved_tests.py`
  - `apps/api/src/kawach/api/v1/commits.py`
  - `apps/api/src/kawach/api/v1/webhooks.py`
  - `apps/api/src/kawach/integrations/github/client.py`
  - `apps/api/src/kawach/integrations/github/__init__.py`
  - `apps/api/tests/test_commit_loop.py`
  - `apps/api/tests/test_scaffolding.py`
  - `apps/api/tests/test_a1_hardening.py`
  - `packages/contracts/openapi.json`
  - `packages/contracts/types.ts`
  - `apps/web/src/generated/api-types.ts`
  - `docs/SCAFFOLD_STATUS.md`
  - `LOG.md`
- **Verified:**
  - `pytest apps/api/tests/test_commit_loop.py`: 5 passed in 3.79s.
  - `pytest apps/api/tests/`: 111 passed, 1 skipped in 73.80s (100% green, +5 new tests over Groq baseline).
  - `lint-imports`: 5 contracts KEPT, 0 broken.
  - `npm run build` in `apps/web`: 100% clean Turbopack build with 13 static pages.
### START FGA — Frontend Gap Audit & Source of Truth Verification
- **Goal:**
  1. Regenerate `packages/contracts/openapi.json` from running backend and build exact endpoint catalog (method, path, auth, schemas, sync/async, idempotency).
  2. Inventory agentic capabilities and data structures across state-graph AppMap, multi-level test cases, coverage matrix, live exploration cockpit, bug verification, saved tests, regression runs, commit loop, localization, and auto-fix.
  3. Map and classify every backend endpoint and agentic capability against `apps/web` (COMPLETE, PARTIAL, MOCKED, STUB-ONLY, MISSING, N/A-BACKEND-NOT-READY).
  4. Test running stack with real API requests and Playwright browser interaction, capturing UI states and screenshots in `docs/frontend-audit/screenshots/`.
  5. Produce canonical, actionable `docs/FRONTEND_GAP_REPORT.md` and machine-readable `docs/frontend-audit/coverage.json`.
- **Planned Files:**
  - `packages/contracts/openapi.json`
  - `packages/contracts/types.ts`
  - `apps/web/src/generated/api-types.ts`
  - `docs/FRONTEND_GAP_REPORT.md`
  - `docs/frontend-audit/coverage.json`
  - `docs/frontend-audit/screenshots/`
### DONE FGA — Frontend Gap Audit & Source of Truth Verification
- **Changed:**
  1. Regenerated canonical OpenAPI 3.1.0 schema (`packages/contracts/openapi.json`) with all 63 paths / 73 operations directly from running FastAPI `create_app()`.
  2. Regenerated TypeScript definitions (`packages/contracts/types.ts` and `apps/web/src/generated/api-types.ts`).
  3. Built live audit runner (`docs/frontend-audit/audit_api.py`) and verified all 73 operations against live backend with JWT session and API token (`kw_live_...`). Saved captured responses into `docs/frontend-audit/api-samples/`.
  4. Executed automated Playwright browser test suite (`docs/frontend-audit/audit_playwright.mjs`) in Chromium against running Next.js web application (`http://localhost:3000`). Tested 18 routes, responsive viewports (1440px, 768px, 375px), and captured 19 full-page UI screenshots in `docs/frontend-audit/screenshots/`.
  5. Produced machine-readable `docs/frontend-audit/coverage.json` classifying all 73 operations: 19 COMPLETE (26.0%), 37 PARTIAL (50.7%), 2 STUB-ONLY (2.7%), 15 MISSING (20.6%).
  6. Discovered and documented 4 critical defects:
     - D-01: Broken run links in `projects/[projectId]/page.tsx` causing HTTP 404.
     - D-02: Permanent empty state in AppMap tab caused by legacy `root_node` lookup instead of `states`/`edges`.
     - D-03: Real-time SSE stream route requesting `/api/runs/...` (404) instead of `/api/v1/runs/...`.
     - D-04: Backend 500 on `PUT/DELETE /api/v1/projects/:id` due to missing methods in `ProjectRepository`.
  7. Authored comprehensive, self-contained `docs/FRONTEND_GAP_REPORT.md` providing complete implementation specifications, acceptance criteria, agentic UI requirements, cross-cutting recommendations, and a 3-milestone build plan.
- **Files:**
  - `packages/contracts/openapi.json`
  - `packages/contracts/types.ts`
  - `apps/web/src/generated/api-types.ts`
  - `docs/frontend-audit/coverage.json`
  - `docs/frontend-audit/endpoint_inventory.json`
  - `docs/frontend-audit/playwright_audit_results.json`
  - `docs/frontend-audit/screenshots/` (19 full-page PNG captures)
  - `docs/frontend-audit/api-samples/` (73 JSON response captures)
  - `docs/FRONTEND_GAP_REPORT.md`
  - `LOG.md`
- **Verified:**
  - Automated endpoint test runner completed with 73 operations executed and captured.
  - Automated Playwright browser audit in Chromium completed with 19 screenshots captured across desktop and mobile.
  - Turbopack compilation clean (`apps/web` builds 13 static pages with 0 TypeScript errors).
- **Unblocked:**
  - Complete engineering roadmap and specifications unblocking frontend implementation for Hackathon demo tracks.












