# SCAFFOLD STATUS — New Product Flow Architecture

This document tracks the scaffolding status of the target regression and auto-fix loop:
**Project -> Saved tests -> Commit trigger -> Run -> Localize -> Suggest fix -> (optional) auto-fix PR**
as specified in Section 8 and Appendix A of the architecture contracts.

> [!IMPORTANT]
> **Scaffold Boundary Notice:**
> All files listed below are structural scaffolding and interfaces only. No new-flow business logic is implemented.
> All API endpoints return `501 Not Implemented`, and services/agents raise `NotImplementedError`.
> Security-critical primitives (`webhook_signature.py`, `domain/policies.py`, `integrations/github/policy.py`) are fully functional and tested.

---

## 1. Scaffold Inventory Table

| Component / Layer | File Path | Status | Notes & Invariants |
|---|---|---|---|
| **DB Models** | `kawach.db.models.saved_tests` | Active (Schema) | `SavedTest`, `SavedTestCoverage`, `RunSelectedTest` |
| **DB Models** | `kawach.db.models.commit_loop` | Active (Schema) | `CommitEvent`, `FailureAnalysis`, `FailureCandidate`, `FixSuggestion` |
| **Pydantic Schemas** | `kawach.schemas.saved_tests` | Scaffold | `SavedTestCreate`, `SavedTestRead`, `RunSelectedTestsRequest` |
| **Pydantic Schemas** | `kawach.schemas.commit_loop` | Scaffold | `CommitEventCreate`, `FailureAnalysisRead`, `FixSuggestionRead` |
| **Pydantic Schemas** | `kawach.schemas.integrations` | Scaffold | `GitHubIntegrationCreate`, `GitHubWebhookPayload` |
| **Domain Policies** | `kawach.domain.policies` | Active / Tested | `is_small_fix()`, `classify_fix_risk()`, `is_fix_allowed()` |
| **GitHub Policy** | `kawach.integrations.github.policy` | Active / Tested | Invariant: `ALLOW_DIRECT_PUSH = False`, `AUTO_FIX_TARGET = "pull_request"` |
| **Webhook Verifier** | `kawach.integrations.github.webhook_signature` | Active / Tested | HMAC-SHA256 verification and delivery ID idempotency |
| **GitHub Client** | `kawach.integrations.github.client` | Active / Tested | Local-first git diff & tree inspection, PR comment formatting |
| **Saved Test Service** | `kawach.services.saved_test_service` | Active / Tested | Script artifact storage (SHA-256), coverage touchpoint indexing, CRUD |
| **Regression Service**| `kawach.services.regression_service` | Active / Tested | Diff-aware test selection, commit triggers, regression run initiation |
| **Workflow Graph** | `kawach.workflows.regression` | Active / Tested | LangGraph state machine with 6 real nodes (select, run, verify, localize, fix, validate) |
| **API Endpoints** | `kawach.api.v1.saved_tests` | Active / Tested | `GET/POST /projects/{id}/saved-tests`, `DELETE .../{test_id}` |
| **API Endpoints** | `kawach.api.v1.commits` | Active / Tested | `GET/POST /projects/{id}/commits`, `/analysis`, `/suggest-fix` (GET read-only & POST generate), `/auto-fix` |
| **API Endpoints** | `kawach.api.v1.regression_runs` | Active / Tested | `POST /api/v1/projects/{id}/regression-runs` (scope `runs:write`, idempotent) |
| **API Endpoints** | `kawach.api.v1.webhooks` | Active / Tested | `POST /api/v1/webhooks/github` (HMAC verified, triggers regression) |
| **Service Interface** | `kawach.services.localization_service` | Scaffold (501/NIE) | `LocalizationServiceProtocol`, `LocalizationService` |
| **Service Interface** | `kawach.services.fix_service` | Scaffold (501/NIE) | `FixServiceProtocol`, `FixService` |
| **Agent Interface** | `kawach.agents.localizer.interface` | Scaffold (NIE) | `LocalizerAgentProtocol`, `LocalizerAgent` |
| **Agent Interface** | `kawach.agents.fix_suggest.interface` | Scaffold (NIE) | `FixSuggesterAgentProtocol`, `FixSuggesterAgent` |
| **DB Models** | `kawach.db.models.identity.ApiToken` | Active / Tested | API tokens with SHA-256 hash at rest, prefix, scopes, revocation |
| **Audit Log** | `kawach.db.models.audit.AuditLog` | Active / Tested | Added `client_type` ("web" \| "github" \| "mcp") |
| **Pydantic Schemas** | `kawach.schemas.tokens` | Active / Tested | `ApiTokenCreate`, `ApiTokenRead`, `ApiTokenCreated`, `ApiClient` |
| **Pydantic Schemas** | `kawach.schemas.catalog` | Active / Tested | Extended `TestCase` (`depth`, `edgeTags`, `riskScore`, `coverageRef`), `Step`, `CoverageMatrix` |
| **Pydantic Schemas** | `kawach.schemas.app_map` | Active / Tested | Extended `StateNode`, `ActionEdge` (with `depth`), `Journey`, `FrontierState` |
| **Explorer Crawler** | `apps/runner/explore.ts` | Active / Tested | State-graph exploration, L0–L3+ frontier priority queue, DOM+UI state fingerprinting, loop/stuck watchdog, a11y & signal tracking |
| **Explorer Agent** | `kawach.agents.explorer` | Active / Tested | Multi-depth execution coordinator, journey extractor (depth >= 3), AppMap assembler with untrusted LLM summary |
| **Planner Agent** | `kawach.agents.planner` | Active / Tested | Multi-level test generation (4 archetypes: single-step, journey, deep-path, edge-case), 14-category edge library, risk scoring, coverage matrix |
| **Reviewer Agent** | `kawach.agents.reviewer` | Active / Tested | Autonomous catalog review with approve/reject powers and logged audit reasons |
| **Token Service** | `kawach.services.token_service` | Active / Tested | Token lifecycle, scoping, verification, audit logging |
| **API Endpoints** | `kawach.api.v1.tokens` | Active / Tested | `POST /api/v1/auth/tokens`, `GET`, `DELETE .../{id}` (session-only) |
| **Test Runner** | `kawach.execution.runner` | Active / Tested | Multi-step execution, checkpoint failure reporting (`failed at step k of n, depth d`), worker state reset, infra flake retry gating |
| **Exploratory Engine**| `kawach.execution.exploratory` | Active / Tested | Deepest frontier mutation planner (reorder, interrupt, repeat, perturb), loop watchdog, path shrinker |
| **Triage Deduplication**| `kawach.execution.triage` | Active / Tested | Defect deduplication by `(failing state, symptom signature)`, minimal Playwright repro script writer |
| **Replay Verifier** | `kawach.execution.verifier` | Active / Tested | Standalone LLM-free 3x deterministic replay certification (`confirmed`, `flaky`, `not_reproduced`) |
| **Pydantic Schemas** | `kawach.schemas.results` | Active / Tested | Added `failedStep`, `totalSteps`, `depth`, `checkpoint` to `TestResult` |
| **Pydantic Schemas** | `kawach.schemas.bug` | Active / Tested | Added `depth`, `failingPath`, `checkpoint`, `reproductionScript` to `Bug` |
| **Use-Case Catalogue**| `docs/USE_CASES.md` | Active | 11 core use-cases mapped across Web, GitHub, MCP doors |
| **MCP Adapter** | `apps/mcp` (`kawach_mcp`) | Complete & Integrated (M5) | 23 tools, 5 resources, 4 prompts; 52 unit/integration tests passing; 100% OpenAPI parity; stdio client subprocess verified; 6th import-linter contract enforced |
| **Contracts & Types** | `packages/contracts/openapi.json` | Active (65 paths)| Exported OpenAPI 3.1.0 schema & generated TypeScript types |


## 2. Scaffolded API Routes (HTTP 501 Not Implemented)

| HTTP Method | Route | Description | Auth / Security |
|---|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/saved-tests` | List saved test library | Scoped to project owner |
| `POST` | `/api/v1/projects/{project_id}/saved-tests` | Save test from run to library | Scoped to project owner |
| `DELETE` | `/api/v1/projects/{project_id}/saved-tests/{test_id}` | Delete saved test | Scoped to project owner |
| `GET` | `/api/v1/projects/{project_id}/commits` | List tracked commit events | Scoped to project owner |
| `POST` | `/api/v1/projects/{project_id}/commits` | Trigger commit regression run | Scoped to project owner |
| `GET` | `/api/v1/projects/{project_id}/commits/{commit_id}/analysis` | Get failure localization report | Scoped to project owner |
| `POST` | `/api/v1/projects/{project_id}/commits/{commit_id}/suggest-fix` | Generate fix patch | Scoped to project owner |
| `POST` | `/api/v1/projects/{project_id}/commits/{commit_id}/auto-fix` | Create PR for validated fix | Scoped to project owner |
| `POST` | `/api/v1/webhooks/github` | Ingest GitHub push/PR event | HMAC-SHA256 signature verified |

---

## 3. Structural Design Principles Verified

1. **Diff-Aware Test Selection:**
   - Database tables `SavedTestCoverage` and `RunSelectedTest` model the relationship between saved Playwright scripts and application pages/components.
2. **Pull Requests Only (Zero Direct Pushes):**
   - Architectural invariant hardcoded in `kawach.integrations.github.policy`: `ALLOW_DIRECT_PUSH = False`.
3. **Objective "Small Fix" Definition:**
   - `kawach.domain.policies.is_small_fix()` classifies fixes based on configurable bounds (max 1 file, max 50 lines) and strictly blocks sensitive paths (`auth`, `login`, `payment`, `billing`, `migrations`, `security`, `.env`).
4. **Fix Verification Reuse:**
   - `kawach.db.models.bugs.Verification.kind` supports `"fix_validation"`, enabling 3x replay verification to prove defect resolution before PR creation.
5. **Untrusted Content Sandboxing:**
   - Any external repository code, commit message, or diff ingested via commit loop is wrapped in `<untrusted_content>` tags via `kawach.llm.prompts.untrusted()`.
