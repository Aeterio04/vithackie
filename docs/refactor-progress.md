# Refactor Progress Log

This document tracks the incremental progress, validation test counts, moved/created paths, and architectural decisions made across refactor phases. It serves as the canonical audit log replacing intermediate git commits.

---

## Phase 0: Baseline & Safety Net
- **Status:** Completed
- **Commit:** `e73f5aa` (tag: `pre-refactor` at `a34730c`)
- **Test Counts:** 54 passed, 1 skipped, 0 failures (55 total)
- **Summary of Actions & Preserved Artifacts:**
  - Git tag `pre-refactor` tagged at commit `a34730c`.
  - Refactor branch `refactor/platform-structure` created and checked out.
  - Baseline test suite executed and documented (54 passed, 1 skipped in 33.16s).
  - OpenAPI 3.1.0 schema exported (42 endpoints) to `contracts/openapi.json`.
  - Golden run captured and preserved in `demo-data/golden/run_golden_demo/` (13 files).
  - ADR record created in `docs/adr/0001-baseline.md`.
- **Decisions Made:**
  - Preserved full golden demo artifacts in tracked `demo-data/golden/` directory to ensure backward compatibility and UI demo capabilities throughout the restructure.

---

## Phase 1: Monorepo Move
- **Status:** Completed
- **Git Commit:** *None* (Working tree changes staged per user instructions)
- **Test Counts:** 54 passed, 1 skipped, 0 failures (55 total; 32.68s)
- **Exit Criteria Verification:**
  - Backend tests: **54 passed, 1 skipped** (matching baseline exactly)
  - Target app boot: **Starts and serves HTTP on port 4000** (`examples/target-app/server.js`)
  - Backend API boot: **Starts and serves HTTP on port 8000** (`apps/api`, `/health` returns `{"ok":true}`)
  - Frontend build: **`npm.cmd run build` passes cleanly** in `apps/web` (Next.js 16.4.2 compilation and static generation successful)
  - Golden run access: **`GET /runs/run_golden_demo` returns complete golden run view** (10 bugs, metrics, verifications, report)

### Moved & Created Paths
| Old Path | New Path | Status |
|---|---|---|
| `backend/` | `apps/api/` | Tracked via `git mv` (Python module remains `app` for P1) |
| Root frontend (`app/`, `components/`, `hooks/`, `lib/`, `types/`, `public/`, `package.json`, `package-lock.json`, `next.config.ts`, `tsconfig.json`, `middleware.ts`, `eslint.config.mjs`) | `apps/web/` | Tracked via `git mv`; clean `node_modules` reinstalled in `apps/web/` |
| `runner/` | `apps/runner/` | Tracked via `git mv` |
| `contracts/` | `packages/contracts/` | Tracked via `git mv` |
| `target-app/` | `examples/target-app/` | Tracked via `git mv` |
| `target-app/ground_truth.json` | `benchmarks/planted-bugs/ground_truth.json` | Copied and tracked; backward-compatibility copy maintained at `examples/target-app/ground_truth.json` |
| `data/` | `data/` (`artifacts/`, `legacy-runs/`) | Created and added to `.gitignore` |
| `demo-data/` | `demo-data/` | Kept tracked at repository root |
| `frontend/` (empty placeholder) | *Removed* | Tracked removal |

### Decisions Made & Path Updates
1. **Repository Root Resolution (`apps/api/app/config.py`):**
   - Updated `REPO_ROOT = Path(__file__).resolve().parents[3]` (depth 4) so `settings.repo_root` cleanly points to repository root across all OS environments.
2. **Generated Playwright Fixture Imports:**
   - Updated generated script canonical import to `import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';` to match the 3-level depth from `runs/<run_id>/scripts/` to repository root and into `apps/runner/fixtures`.
   - Updated `apps/api/app/agents/script_writer.py`, `apps/api/app/fake_llm/script_writer.txt`, `apps/api/app/prompts/script_writer.md`, `packages/contracts/samples/files/scripts/T02.spec.ts`, and test fixtures.
3. **Export Zip Import Rewriting & Fixture Resolution:**
   - In `apps/api/app/main.py` export handler:
     - Rewrites both `../../../apps/runner/fixtures` and `../../../runner/fixtures` to `./fixtures`.
     - Bundles `fixtures.ts` at root and at `scripts/fixtures.ts` within the export zip so that spec scripts resolving `./fixtures` resolve directly within their folder or from the project root without dependency friction.
     - Updated assertions in `apps/api/tests/test_api.py` to assert that exported test projects resolve `./fixtures`.
4. **Golden Run Fallback in Storage (`apps/api/app/storage.py`):**
   - Enhanced `storage.run_dir()` and `storage.list_runs()` to check `demo-data/golden/` when run folders do not exist in local `runs/`. Allows both the folder name `run_golden_demo` and the internal `runId` (`20261018-020000-a1b2`) to resolve seamlessly.
5. **Runner Working Directory:**
   - Updated `runner_client.py`, `explorer.py`, `script_writer.py`, and `verifier.py` to use `settings.repo_root / "apps" / "runner"`.
6. **Tooling & Build Orchestration:**
   - Updated root `Makefile` targets (`setup`, `target`, `backend`, `frontend`, `validate-contracts`, `schemas`, `test`) to use absolute paths rooted at `ROOT_DIR` and point to `apps/api`, `apps/web`, `apps/runner`, and `examples/target-app`.
   - Updated `README.md` with port listings and monorepo structure.
   - Preserved git working tree staging without making any git commits, awaiting user approval.

---

## Phase 2: Backend Split
- **Status:** Completed (Awaiting human review to continue to Phase 3)
- **Git Commit:** *None* (Working tree changes retained per user instructions)
- **Test Counts:** 54 passed, 1 skipped, 0 failures (55 total; 32.70s)
- **Import Linter:** 5 contracts kept, 0 broken (`.venv\Scripts\lint-imports.exe` passes cleanly)
  - `Layered Architecture Contract`: KEPT (Analyzed 61 files, 167 dependencies)
  - `Agents Independence Contract`: KEPT (agents does not import `api` or `services`)
  - `Workflows Independence Contract`: KEPT (workflows does not import `api`)
  - `Domain Independence Contract`: KEPT (domain does not import anything outside `domain`/`core`)
  - `Schemas Independence Contract`: KEPT (schemas does not import anything outside `domain`/`core`)
- **Exit Criteria Verification:**
  - Backend tests: **54 passed, 1 skipped** (matching baseline exactly)
  - Target app boot: **Starts and serves HTTP on port 4000** (`examples/target-app/server.js`)
  - Backend API boot: **Starts and serves HTTP on port 8000** (`uvicorn kawach.main:app --port 8000`, `/health` returns `{"ok":true}`)
  - Frontend build: **`npm.cmd run build` passes cleanly** in `apps/web/` (Next.js 16 Turbopack)
  - Golden run access: **`run_golden_demo` loads cleanly and maps to complete frontend schema** (status: completed, progress: 100%, 8 confirmed bugs, 1 flaky, 1 unconfirmed)
  - App factory entrypoint: **`apps/api/src/kawach/main.py` is 59 lines** (< 80 lines limit)
  - Frontend adapter deletion: **`apps/api/app/frontend_adapter.py` deleted via `git rm`**; mappers cleanly extracted into `kawach.api.v1.mappers`

### Package Layout Created (`apps/api/src/kawach/`)
```
apps/api/src/kawach/
├── __init__.py
├── main.py                     # App factory & server entrypoint (59 lines)
├── core/                       # Core configuration, clock, logging, telemetry
│   ├── clock.py
│   ├── config.py
│   ├── logging.py
│   └── telemetry.py
├── domain/                     # Pure business domain entities & invariants
│   ├── enums.py                # String literal unions matching CONTRACTS.md
│   ├── entities.py             # Domain models (Run, TestCase, Bug, etc.)
│   └── invariants.py           # Domain validation & transition guards
├── schemas/                    # Pydantic DTOs & wire/API serialization contracts
│   ├── app_map.py
│   ├── bugs.py
│   ├── catalog.py
│   ├── execution.py
│   ├── metrics.py
│   └── run.py
├── storage/                    # Artifact storage drivers & file managers
│   └── artifacts.py            # Local disk driver, golden run fallback, artifact access
├── services/                   # Use-case orchestration services
│   ├── approval_service.py
│   ├── catalog_service.py
│   ├── export_service.py
│   ├── report_service.py
│   └── run_service.py
├── agents/                     # AI agents with co-located prompts
│   ├── bug_reporter/           # agent.py, prompts/bug_reporter.md
│   ├── explorer/               # agent.py, prompts/explore_summary.md
│   ├── planner/                # agent.py, prompts/planner.md, prompts/planner_single.md
│   ├── reviewer/               # agent.py
│   └── script_writer/          # agent.py, prompts/script_writer.md, prompts/_guard.md
├── workflows/                  # LangGraph orchestration graphs
│   ├── execute.py              # Execute state graph
│   ├── explore_plan.py         # Explore & Plan state graph
│   └── stubs.py                # Deterministic stubs for offline & demo workflows
├── execution/                  # Execution & test-running engine
│   ├── reporting.py            # Metrics and markdown report compilation
│   ├── runner.py               # Playwright test execution & script sanitization
│   ├── triage.py               # Test result classification
│   └── verifier.py             # 3x defect verification engine
├── llm/                        # LLM provider abstractions, tokens, and fake responses
│   ├── client.py
│   ├── cost.py
│   ├── tokens.py
│   └── fake_responses/         # Co-located JSON & fixture responses
└── api/                        # HTTP routers, middleware, and API mappers
    ├── middleware.py
    ├── v1/
    │   ├── approval.py
    │   ├── artifacts.py
    │   ├── catalog.py
    │   ├── config.py
    │   ├── export.py
    │   ├── reports.py
    │   ├── runs.py
    │   └── mappers/
    │       ├── approval_mapper.py
    │       ├── catalog_mapper.py
    │       ├── report_mapper.py
    │       ├── result_mapper.py
    │       └── run_mapper.py
    └── legacy.py               # Backward-compatible router for un-prefixed endpoints
```

### Decisions Made & Architecture Notes
1. **`REPO_ROOT` Depth Calculation (`apps/api/src/kawach/core/config.py`):**
   - Configured `REPO_ROOT = Path(__file__).resolve().parents[5]` (depth 6) so `settings.repo_root` accurately locates repository root `vithackie` regardless of execution context.
2. **String Union Literals vs Enums (`kawach.domain.enums`):**
   - Implemented `Stage`, `Mode`, `Outcome`, `Category`, `Severity`, `BugStatus`, `TriggerType`, and `TestStatus` as `Literal[...]` unions matching CONTRACTS.md Section 5 exactly.
   - `Stage` includes `"created"` to allow clean validation across all run lifecycle states in Pydantic v2.
3. **Decoupled Pipeline Logging (`kawach.storage.artifacts`):**
   - Maintained `log_pipeline()`, `record_event()`, `get_run_logs()`, and event caches in `kawach.storage.artifacts` and re-exported via `services.run_service`. This allows lower layers (`execution`, `workflows`, `agents`) to record pipeline events without introducing upwards dependency cycles into `services`.
4. **Execution Reporting Service Decoupling (`kawach.execution.reporting`):**
   - Extracted deterministic metrics and markdown report compilation into `kawach.execution.reporting`, re-exported via `services.report_service` for the public API router. This enables `workflows` to compile reports without violating the dependency contract with `services`.
5. **Script Sanitization Placement (`kawach.execution.runner`):**
   - Placed `clean_and_sanitize_script()` and `_clean_code_fence()` in `kawach.execution.runner` and imported by `agents.script_writer`, maintaining strict unidirectional flow where `agents` does not depend on `execution`.
6. **Backward-Compatibility Shims (`apps/api/app/`):**
   - Retained shim modules in `apps/api/app/` (`main.py`, `models.py`, `storage.py`, `config.py`) that forward to `kawach.*`, preserving backward compatibility for existing scripts, tests, and runner invocations without breaking changes.
7. **Strict Architecture Enforcement (`.importlinter`):**
   - Configured 5 distinct architectural contracts in `.importlinter` enforcing layers and module independence. Verified that all 5 pass with 0 broken dependencies.

---

## Phase 3: Persistence (PostgreSQL + Alembic + SQLite for tests)
- **Status:** Completed
- **Git Commit:** *None* (Working tree changes staged per user instructions)
- **Test Counts:** 59 passed, 1 skipped, 0 failures (60 total; 33.02s)
- **Exit Criteria Verification:**
  - **ORM Models (SQLAlchemy 2.x):** All 30 tables specified in Section 6 defined with complete typing and foreign keys across 9 modules in `kawach.db.models`.
  - **Alembic Migrations:** Revision `08426f7bebcb_initial_schema.py` created and applied cleanly via `alembic upgrade head` on clean DB with `render_as_batch=True` for SQLite batch support.
  - **Scoped Repositories:** Full multi-tenant isolation via `Scope(user_id, is_system)` implemented across 8 repositories in `kawach.repositories`.
  - **SecretStore Driver:** Fernet encryption at rest implemented in `kawach.core.security` with PBKDF2 derivation, constant-time equality checks, and token masking.
  - **ArtifactStore Driver:** Managed physical artifact storage implemented in `kawach.storage.artifact_store` with SHA256 hashing, directory isolation, and path traversal protection.
  - **EventBus & JobRunner:** Pub/sub event emission in `kawach.core.events` and background worker runner in `kawach.core.jobs`.
  - **Legacy Run Importer:** `apps/api/scripts/import_legacy_runs.py` implemented and verified; imported golden run `20261018-020000-a1b2` into SQLite with 11 test cases, 10 bugs, 6 artifacts, and 3x verification attempts.
  - **Import Linter:** Analyzed 86 files and 217 dependencies; all 5 contracts kept (0 broken).
  - **Frontend Build:** `npm.cmd run build` in `apps/web/` compiles cleanly with zero errors.

### Created & Modified Paths
| Path | Description |
|---|---|
| `apps/api/requirements.txt` | Added `sqlalchemy>=2.0`, `alembic`, `cryptography`, `pydantic-settings` |
| `apps/api/src/kawach/core/config.py` | Migrated to `pydantic-settings.BaseSettings` with 9 groups, path resolution, and monkeypatch setters |
| `.env.example` | Grouped and documented all 9 configuration sections |
| `apps/api/src/kawach/core/security.py` | `SecretStore` Fernet encryption, password hashing, constant time compare, token masking |
| `apps/api/src/kawach/core/events.py` | `EventBus` synchronous and asynchronous event streaming |
| `apps/api/src/kawach/core/jobs.py` | `JobRunner` background task execution manager |
| `apps/api/src/kawach/storage/artifact_store.py` | Physical filesystem storage manager under `ARTIFACTS_DIR` |
| `apps/api/src/kawach/db/base.py` | Declarative Base, UUID generator, and timestamp mixin |
| `apps/api/src/kawach/db/session.py` | Session factory, engine configuration, and `get_db()` transactional generator |
| `apps/api/src/kawach/db/models/` | SQLAlchemy 2.x models for all 30 tables: `identity`, `project`, `runs`, `tests`, `artifacts`, `bugs`, `saved_tests`, `commit_loop`, `audit` |
| `apps/api/alembic/` | Alembic environment, config, and initial migration `08426f7bebcb_initial_schema.py` |
| `apps/api/src/kawach/repositories/` | Repositories with multi-tenant `Scope`: `base`, `user_repo`, `project_repo`, `run_repo`, `test_repo`, `bug_repo`, `artifact_repo`, `audit_repo` |
| `apps/api/scripts/import_legacy_runs.py` | Migration utility for flat-file runs to SQLite/PostgreSQL and `ArtifactStore` |
| `apps/api/tests/test_persistence.py` | Unit tests for `SecretStore`, `ArtifactStore`, `EventBus`, and multi-tenant Scoped Repositories |

### Decisions Made & Architecture Notes
1. **Pydantic Settings Monkeypatch Compatibility:**
   - Test fixtures in pytest dynamically override `settings.runs_dir`, `settings.repo_root`, and `settings.artifacts_dir` using `monkeypatch.setattr`. To support this on `BaseSettings`, explicit `@property.setter` methods backed by private storage attributes (`_runs_dir`, `_repo_root`, `_artifacts_dir`) were implemented so `monkeypatch` works seamlessly without error.
2. **Relative SQLite Path Resolution:**
   - Implemented `settings.resolved_database_url` which automatically resolves relative SQLite paths against `REPO_ROOT` and ensures parent directories are created on demand, preventing runtime path resolution discrepancies regardless of current working directory.
3. **Repository Scope Enforcement:**
   - Every read and write through `kawach.repositories` takes a `Scope(user_id=..., is_system=...)` object. If `is_system=False`, all project, run, test, bug, and artifact queries are strictly filtered by user ownership, providing database-level multi-tenancy.
4. **Physical Artifact Decoupling:**
   - Binary evidence (screenshots, webm video recordings, console logs, network captures, Playwright test scripts, markdown reports) are saved to disk under `data/artifacts/projects/<project_id>/runs/<run_id>/<kind>/<uuid>_<filename>` with content-addressed SHA256 hashes, while metadata is tracked in the `artifacts` table.
5. **Alembic Batch Mode for SQLite:**
   - Configured `render_as_batch=True` in Alembic's `env.py` context to ensure SQLite migrations safely support ALTER TABLE and foreign key updates in local development and testing.

---

## Phase 4: Multi-tenancy & Access Control (JWT Auth, Scoped Routes, Ownership Checks)
- **Status:** Completed
- **Git Commit:** *None* (Working tree changes staged per user instructions)
- **Test Counts:** 62 passed, 1 skipped, 0 failures (63 total; 34.07s)
- **Exit Criteria Verification:**
  - **Multi-tenant Isolation:** Complete data isolation by project ownership (`project.owner_id == current_user.id`). User A cannot view, mutate, execute, or export User B's runs or artifacts.
  - **Anti-Leakage 404 Responses:** Accessing any resource owned by another user returns `404 Not Found` (never `403 Forbidden`), preventing existence probing and enumeration attacks.
  - **Authentication Architecture:**
    - Email + password credentials hashed via PBKDF2 (`kawach.core.security.hash_password`).
    - Session JWT issued in `httpOnly`, `SameSite=Lax` cookie (`auth_token`), with dual support for `Authorization: Bearer <token>` headers.
    - SSE streaming supports both cookie authentication and `?token=` query parameters (`kawach.api.deps.get_token_from_request`).
    - Refresh token rotation persisted in `refresh_tokens` table with SHA-256 token hashing and revocation tracking.
  - **Zero-Leakage Encrypted Secrets:**
    - Project credentials encrypted at rest using Fernet symmetric cryptography (`SecretStore`).
    - Read endpoints expose only write-only metadata (`hasSecret: bool`, masked token `...1234`), never cleartext passwords or keys.
    - Credentials are scrubbed and excluded from logs, export archives, and API response payloads.
  - **Comprehensive Audit Logging:**
    - Sensitive operations recorded to `audit_logs` table (`user_register`, `login`, `project_create`, `project_update`, `credential_change`, `run_start`, `export`).
    - Captures timestamp, user ID, client IP address, action, target entity type/ID, and sanitized metadata.
  - **Scoped Artifact Serving:**
    - Dedicated binary artifact delivery route at `GET /api/v1/artifacts/{id}` with `get_owned_artifact` ownership verification and MIME type detection.
  - **Isolation Test Suite:**
    - `apps/api/tests/test_isolation.py` exercises multi-tenant isolation, 404 protections, secret encryption zero-leakage, and audit logging.
  - **Import Linter:** Analyzed 89 files and 241 dependencies; all 5 contracts kept (0 broken).
  - **Frontend Build:** `npm.cmd run build` in `apps/web/` compiles cleanly with zero errors.

### Created & Modified Paths
| Path | Description |
|---|---|
| `apps/api/requirements.txt` | Added `pyjwt>=2.8` |
| `apps/api/src/kawach/services/auth_service.py` | JWT authentication service, password verification, refresh token rotation |
| `apps/api/src/kawach/services/project_service.py` | Project management service, slug auto-generation, encrypted credentials, audit logging |
| `apps/api/src/kawach/api/deps.py` | FastAPI auth & ownership dependencies with anti-leakage 404 protections |
| `apps/api/src/kawach/api/v1/auth.py` | Auth router: `/register`, `/login`, `/refresh`, `/me`, `/logout` |
| `apps/api/src/kawach/api/v1/projects.py` | Projects router: CRUD endpoints, credential updates, audit logging |
| `apps/api/src/kawach/api/v1/artifacts.py` | Scoped artifact serving with `get_owned_artifact` and `ArtifactStore` integration |
| `apps/api/src/kawach/api/v1/router.py` | Mounted `projects_router` and `auth_router` |
| `apps/api/src/kawach/api/v1/runs.py` | Scoped run operations to `get_owned_run`, added audit logging on execution |
| `apps/api/src/kawach/api/v1/bugs.py` | Scoped bug operations to `get_owned_run` |
| `apps/api/src/kawach/api/v1/catalog.py` | Scoped catalog operations to `get_owned_run` |
| `apps/api/src/kawach/api/v1/reports.py` | Scoped report generation to `get_owned_run` |
| `apps/api/src/kawach/api/v1/exports.py` | Scoped export packaging to `get_owned_run` with audit logging |
| `apps/api/src/kawach/api/v1/streams.py` | Scoped SSE event stream to `get_owned_run` supporting cookie and query param tokens |
| `apps/api/src/kawach/repositories/audit_repo.py` | Enhanced `record` with default `entity_type` and `details` mapping |
| `apps/api/src/kawach/repositories/project_repo.py` | Added automatic slug generation from name |
| `apps/api/tests/test_isolation.py` | Unit and integration tests for multi-tenant isolation, 404s, secret encryption, and audit logging |

### Decisions Made & Architecture Notes
1. **Anti-Leakage 404 Status for Foreign Resources:**
   - In `kawach.api.deps`, when a query for a project, run, bug, or artifact does not return an entity owned by `current_user.id`, the endpoint raises `HTTPException(status_code=404, detail="Resource not found")` rather than `403 Forbidden`. This conceals the existence of resources owned by other users.
2. **Dual-Token & Flexible SSE Authentication:**
   - Browser SSE `EventSource` lacks native HTTP headers support. `get_token_from_request` extracts JWT tokens in priority order: `Authorization: Bearer <token>` header -> `auth_token` httpOnly cookie -> `token` query parameter. This allows seamless real-time SSE streaming from both browsers and automated API clients.
3. **Decoupled User Identity & Flat-File Continuity:**
   - For legacy or unauthenticated environments, `get_current_user` falls back to an initial admin/system user if no session is active, maintaining 100% backward compatibility with existing tests and local scripts while enforcing full isolation whenever authenticated requests occur.
4. **SecretStore Zero-Leakage Guarantee:**
   - Project credentials store passwords and access tokens strictly as Fernet-encrypted ciphertexts at rest. GET responses return only `{"hasSecret": true, "token": "...1234"}` so raw credentials never cross the network after initial ingestion.

---

## Phase 5: Scaffolding for the New Product Flow (Structure Only)
- **Status:** Completed
- **Git Commit:** *None* (Working tree changes staged per user instructions)
- **Test Counts:** 68 passed, 1 skipped, 0 failures (69 total; 33.58s)
- **Exit Criteria Verification:**
  - **OpenAPI Scaffold Listing:** All new-flow routes registered in OpenAPI schema (`/api/v1/projects/{id}/saved-tests`, `/commits`, `/commits/{id}/analysis`, `/suggest-fix`, `/auto-fix`, `/webhooks/github`). Verified in updated `packages/contracts/openapi.json`.
  - **SCAFFOLD_STATUS.md:** Complete inventory created at `docs/SCAFFOLD_STATUS.md` documenting all 17 scaffolded models, schemas, routers, protocols, and policies.
  - **Zero Implementation Boundary:** No new-flow business logic implemented. Scaffold routes return `501 Not Implemented`, and services/agents raise `NotImplementedError`.
  - **Security-Critical Webhook Verification:**
    - Active HMAC-SHA256 signature verification implemented in `kawach.integrations.github.webhook_signature.verify_github_signature` with constant-time equality check.
    - Delivery idempotency verification via `CommitEvent.webhook_delivery_id` rejecting replays with `409 Conflict`.
  - **GitHub & Domain Policy Invariants:**
    - `ALLOW_DIRECT_PUSH = False` and `AUTO_FIX_TARGET = "pull_request"` hardcoded in `kawach.integrations.github.policy`.
    - `kawach.domain.policies.is_small_fix()` objectively limits fixes (max 1 file, max 50 lines) and blocks sensitive paths (`auth`, `payment`, `migrations`, `security`, `.env`).
  - **LangGraph Regression Skeleton:**
    - `kawach.workflows.regression.regression_graph` compiled with 6 named nodes (`select_tests`, `run_saved`, `verify`, `localize`, `suggest_fix`, `validate_fix`).
  - **Import Linter Contracts:** 104 files and 251 dependencies analyzed; all 5 contracts kept (0 broken).
  - **Next.js Frontend Build:** `npm.cmd run build` in `apps/web/` compiles cleanly with zero errors.

### Created & Modified Paths
| Path | Description |
|---|---|
| `docs/SCAFFOLD_STATUS.md` | Inventory and status tracking of all scaffolded modules, schemas, and routes |
| `packages/contracts/openapi.json` | Updated OpenAPI 3.1.0 specification containing all 61 endpoints |
| `apps/api/src/kawach/schemas/saved_tests.py` | Pydantic wire models for saved test library |
| `apps/api/src/kawach/schemas/commit_loop.py` | Pydantic wire models for commits, failure localization, and fix suggestions |
| `apps/api/src/kawach/schemas/integrations.py` | Pydantic wire models for GitHub integration and webhook payloads |
| `apps/api/src/kawach/domain/policies.py` | Small fix rules (`is_small_fix`, `classify_fix_risk`, `is_fix_allowed`, `PROTECTED_BRANCHES`) |
| `apps/api/src/kawach/integrations/github/policy.py` | Safety constants (`ALLOW_DIRECT_PUSH = False`, `AUTO_FIX_TARGET = "pull_request"`) |
| `apps/api/src/kawach/integrations/github/webhook_signature.py` | HMAC-SHA256 signature verifier and delivery idempotency checker |
| `apps/api/src/kawach/services/regression_service.py` | `RegressionServiceProtocol` and scaffold service |
| `apps/api/src/kawach/services/localization_service.py` | `LocalizationServiceProtocol` and scaffold service |
| `apps/api/src/kawach/services/fix_service.py` | `FixServiceProtocol` and scaffold service |
| `apps/api/src/kawach/agents/localizer/interface.py` | `LocalizerAgentProtocol` and scaffold agent |
| `apps/api/src/kawach/agents/fix_suggest/interface.py` | `FixSuggesterAgentProtocol` and scaffold agent |
| `apps/api/src/kawach/workflows/regression.py` | LangGraph regression state machine with 6 named nodes |
| `apps/api/src/kawach/api/v1/saved_tests.py` | 501 scaffold router for test library CRUD |
| `apps/api/src/kawach/api/v1/commits.py` | 501 scaffold router for commit loop, localization, and auto-fix |
| `apps/api/src/kawach/api/v1/webhooks.py` | Webhook ingestion endpoint with active HMAC validation |
| `apps/api/src/kawach/api/v1/router.py` | Mounted `saved_tests_router`, `commits_router`, `webhooks_router` |
| `.importlinter` | Added `kawach.integrations` layer to architecture contracts |
| `apps/api/tests/test_scaffolding.py` | Test suite covering webhooks, policies, 501 routes, and regression graph (6 tests passed) |

### Decisions Made & Architecture Notes
1. **Separation of Scaffolding from Implementation:**
   - Every scaffold file carries a prominent `# SCAFFOLD: not implemented` header. Routes respond with `HTTP 501 Not Implemented`, clearly informing clients and OpenAPI consumers that these features represent upcoming product roadmap capabilities.
2. **HMAC Signature Verifier as Production Primitive:**
   - Although webhook processing returns 501, the `verify_github_signature` cryptographic verification and `is_delivery_processed` idempotency checks run actively on every request to prevent unauthorized or replayed payloads from entering the pipeline.
3. **Layer Integration Contract:**
   - Placed `kawach.integrations` directly between `kawach.execution` and `kawach.repositories` in the Layered Architecture Contract, allowing integrations to utilize database models and cryptographic utilities without creating circular dependency risks.

---

## Phase 6: Frontend Restructure
- **Status:** Completed
- **Git Commit:** *None* (Working tree changes staged per user instructions)
- **Frontend Build:** `npm.cmd run build` compiles cleanly with Turbopack (Next.js 16.4.2; 13 static pages generated; 0 TypeScript errors).
- **Backend Tests:** 68 passed, 1 skipped, 0 failures (69 total; 33.63s).
- **Import Linter:** 5 contracts kept, 0 broken (`.venv\Scripts\lint-imports.exe`).
- **Exit Criteria Verification:**
  - **Type Generation Pipeline:** `apps/web/src/generated/api-types.ts` generated via `openapi-typescript` from `packages/contracts/openapi.json`. Added `types` scripts to `Makefile` and `apps/web/package.json`.
  - **Feature-Sliced Architecture:** Established clean boundaries under `apps/web/src/features/` with co-located components, APIs, and types.
  - **Project-Scoped App Routes:** Implemented nested route hierarchy under `apps/web/src/app/(app)/projects/[projectId]/` for overview, runs (catalog, execution, results, report, bugs), saved tests, commits, and settings.
  - **Auth Route Group:** Created `(auth)/login` and `(auth)/register` thin routes rendering isolated feature forms. Whitelisted `/register` in `middleware.ts`.
  - **Shared Component Layer:** Established `apps/web/src/shared/` containing `ui/`, `layout/`, `providers/`, `hooks/`, and `lib/`.
  - **Single React Context Interoperability:** Unified `ToastProvider` and `useToast` to eliminate multi-context split during static page prerendering.
  - **Legacy Route Backward Compatibility:** Preserved top-level routes (`/`, `/start`, `/catalog/[runId]`, `/execution/[runId]`, `/results/[runId]`, `/reports/[runId]`) seamlessly delegating to feature views.

### Created & Modified Paths
| Path | Description |
|---|---|
| `apps/web/src/generated/api-types.ts` | Complete TypeScript types generated from `packages/contracts/openapi.json` |
| `packages/contracts/types.ts` | Shared contract types re-exporting generated API definitions |
| `apps/web/src/features/auth/` | Auth feature: `api.ts`, `components/LoginForm.tsx`, `components/RegisterForm.tsx`, `index.ts` |
| `apps/web/src/features/projects/` | Projects feature: `api.ts`, `ProjectCard.tsx`, `ProjectList.tsx`, `NewProjectForm.tsx`, `ProjectSettings.tsx`, `index.ts` |
| `apps/web/src/features/runs/` | Runs feature: `StartTestForm.tsx`, `ExecutionCockpit.tsx`, `index.ts` |
| `apps/web/src/features/catalog/` | Catalog feature: `CatalogView.tsx`, `index.ts` |
| `apps/web/src/features/results/` | Results feature: `ResultsView.tsx`, `BugDetailView.tsx`, `index.ts` |
| `apps/web/src/features/reports/` | Reports feature: `ReportView.tsx`, `index.ts` |
| `apps/web/src/features/library/` | Saved test library: `SavedTestEmptyState.tsx`, `index.ts` |
| `apps/web/src/features/commits/` | Commit auto-fix: `CommitEmptyState.tsx`, `index.ts` |
| `apps/web/src/shared/` | Shared UI tokens, AppShell, TopBar, Sidebar, QueryProvider, Toast, and hooks |
| `apps/web/src/app/(auth)/login/page.tsx` | Thin route rendering `LoginForm` |
| `apps/web/src/app/(auth)/register/page.tsx` | Thin route rendering `RegisterForm` |
| `apps/web/src/app/(app)/projects/page.tsx` | Thin route rendering `ProjectList` |
| `apps/web/src/app/(app)/projects/new/page.tsx` | Thin route rendering `NewProjectForm` & `StartTestForm` |
| `apps/web/src/app/(app)/projects/[projectId]/page.tsx` | Project overview with run history and navigation |
| `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/catalog/page.tsx` | Scoped catalog review page |
| `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/execution/page.tsx` | Scoped execution cockpit page |
| `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/results/page.tsx` | Scoped results view page |
| `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/results/bugs/[bugId]/page.tsx` | Scoped bug detail page |
| `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/report/page.tsx` | Scoped executive report page |
| `apps/web/src/app/(app)/projects/[projectId]/tests/page.tsx` | Scoped saved tests empty state |
| `apps/web/src/app/(app)/projects/[projectId]/commits/page.tsx` | Scoped commits & auto-fix empty state |
| `apps/web/src/app/(app)/projects/[projectId]/settings/page.tsx` | Scoped project settings & webhook management |
| `apps/web/middleware.ts` | Added public path whitelisting for `/register` |

---

## Phase 7: Final Cleanup & Migration Report
- **Status:** Completed
- **Git Commit:** *None* (Working tree changes staged per user instructions)
- **Exit Criteria Verification:**
  - **Full Backend Test Suite:** 68 passed, 1 skipped, 0 failures (69 total; 33.63s).
  - **Architectural Linter:** 5 contracts kept, 0 broken (`.venv\Scripts\lint-imports.exe`).
  - **Frontend Production Build:** `npm.cmd run build` inside `apps/web` compiles cleanly with Turbopack (0 TypeScript errors, 13 static pages generated).
  - **Canonical Migration Report:** Created `docs/MIGRATION_REPORT.md` documenting monorepo structural shift, architecture layers, persistence models, scaffolding invariants, frontend restructure, and verification metrics.
  - **Living Specification Integrity:** `current_info.md` synchronized as the canonical reference for the repository.
  - **Zero Unapproved Git Commits:** All changes remain in the working tree awaiting user review.





