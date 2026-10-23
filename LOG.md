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

