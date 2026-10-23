# KAWACH — Service Use-Case Catalogue

> **Architecture Classification:** Unified Service Contract & Gateway Specification  
> **Design Pattern:** Service-First, Three Front Doors (Web, GitHub, MCP)  
> **Status:** Canonical Specification

---

## 1. Overview & Architectural Principles

All application business logic lives in `kawach.services` use-cases.  
The three client entry points (**Web Application**, **GitHub Webhooks / PR Integrations**, and **Model Context Protocol (MCP) Server**) operate as thin protocol adapters that exclusively perform:
1. **Authentication & Authorization** (Resolving tenant `Scope` and caller identity).
2. **Input Validation** (Mapping transport payloads to validated Pydantic models).
3. **Use-Case Execution** (Delegating directly to `kawach.services`).
4. **Output Shaping** (Returning structured summaries and artifact references, never raw untrusted page or repo content).

### Three Front Doors Matrix
| Front Door | Transport Protocol | Authentication Mechanism | Client Identity | Idempotency Support |
|---|---|---|---|---|
| **Web Dashboard** | REST + SSE | HttpOnly Cookie / Bearer JWT | `ApiClient.WEB` | Supported via HTTP Header |
| **GitHub Integration** | Webhook HTTP POST | HMAC-SHA256 (`X-Hub-Signature-256`) | `ApiClient.GITHUB` | Verified via `X-GitHub-Delivery` ID |
| **MCP Server** | stdio JSON-RPC | Per-User Scoped API Token (`kw_...`) | `ApiClient.MCP` | Supported per tool invocation |

---

## 2. Use-Case Catalog

### UC-01: Start Exploration & Planning Run (`start_run`)
- **Summary:** Ingests target URL, spec sheet, credentials, and budgets. Initiates Graph 1 exploration & catalog generation.
- **Service Method:** `kawach.services.RunService.start_run`
- **Inputs:**
  - `scope: Scope` (Tenant identity)
  - `project_id: Optional[str]`
  - `target_url: str`
  - `spec_raw: str`
  - `prompt: Optional[str]`
  - `username: Optional[str]`
  - `password: Optional[str]`
  - `budgets: Optional[Budgets]`
  - `mode: Literal["manual", "autonomous"]`
  - `idempotency_key: Optional[str]`
- **Outputs:** `RunCreatedResponse` (`run_id`, `status`, `stage`, `sse_stream_url`, `created_at`)
- **Execution Mode:** Async (returns run handle immediately; executes in background thread)
- **Exposed By:** Web (`POST /runs`, `POST /api/v1/projects/{id}/runs`), MCP (`start_run`)

### UC-02: Query Run Status & Cockpit Telemetry (`get_run_status`)
- **Summary:** Returns real-time execution progress, active workers, budget consumption, and discovered defect counters.
- **Service Method:** `kawach.services.RunService.get_run_status`
- **Inputs:** `scope: Scope`, `run_id: str`
- **Outputs:** `RunStatusResponse` (status, stage, progress, budgets, active workers, bug counts)
- **Execution Mode:** Sync
- **Exposed By:** Web (`GET /runs/{id}`, `GET /api/v1/projects/{id}/runs/{run_id}`), MCP (`get_run_status`)

### UC-03: Catalog Review Decision (`approve_catalog`)
- **Summary:** Records human or reviewer agent decisions on proposed test cases, transitions run stage from `awaiting_review` to `running`, and triggers Graph 2 execution.
- **Service Method:** `kawach.services.RunService.approve_catalog`
- **Inputs:** `scope: Scope`, `run_id: str`, `decisions: List[ReviewDecision]`, `ad_hoc_tests: Optional[List[TestCase]]`
- **Outputs:** `CatalogApprovalResponse` (`status: "approved"`, `approved_count: int`, `rejected_count: int`)
- **Execution Mode:** Async (triggers Graph 2 execution pipeline)
- **Exposed By:** Web (`POST /runs/{id}/execute`, `PUT /runs/{id}/catalog`), MCP (`approve_catalog`)

### UC-04: Trigger Commit Regression Suite (`run_regression`)
- **Summary:** Diff-aware test selection runs saved tests matching changed files or components, followed by 3x deterministic failure verification.
- **Service Method:** `kawach.services.RegressionService.run_regression`
- **Inputs:**
  - `scope: Scope`
  - `project_id: str`
  - `commit_sha: str`
  - `changed_files: Optional[List[str]]`
  - `branch: Optional[str]`
  - `message: Optional[str]`
  - `idempotency_key: Optional[str]`
- **Outputs:** `RegressionRunHandle` (`run_id`, `commit_sha`, `selected_test_count`, `status`)
- **Execution Mode:** Async (LangGraph regression state machine)
- **Exposed By:** Web (`POST /api/v1/projects/{id}/commits`), GitHub (`POST /api/v1/webhooks/github`), MCP (`run_suite`)

### UC-05: Save Test to Project Library (`save_test`)
- **Summary:** Saves a verified test script from an execution run into the project regression library, calculating SHA-256 and indexing coverage tags.
- **Service Method:** `kawach.services.SavedTestService.save_test`
- **Inputs:**
  - `scope: Scope`
  - `project_id: str`
  - `run_id: str`
  - `test_id: str`
  - `title: Optional[str]`
  - `tags: Optional[List[str]]`
  - `spec_ref: Optional[str]`
- **Outputs:** `SavedTestRead` (`id`, `project_id`, `artifact_id`, `sha256`, `tags`, `created_at`)
- **Execution Mode:** Sync
- **Exposed By:** Web (`POST /api/v1/projects/{id}/saved-tests`), MCP (`save_test` with explicit `confirm=True`)

### UC-06: Query Saved Test Library (`list_saved_tests`)
- **Summary:** Retrieves indexed regression tests for a project with optional tag and requirement filtering.
- **Service Method:** `kawach.services.SavedTestService.list_saved_tests`
- **Inputs:** `scope: Scope`, `project_id: str`, `tag: Optional[str]`, `spec_ref: Optional[str]`
- **Outputs:** `List[SavedTestRead]`
- **Execution Mode:** Sync
- **Exposed By:** Web (`GET /api/v1/projects/{id}/saved-tests`), MCP (`list_saved_tests`)

### UC-07: Delete Saved Test (`delete_saved_test`)
- **Summary:** Soft-deletes or removes a saved regression test from the project library.
- **Service Method:** `kawach.services.SavedTestService.delete_saved_test`
- **Inputs:** `scope: Scope`, `project_id: str`, `saved_test_id: str`
- **Outputs:** `SuccessResponse` (`ok: True`)
- **Execution Mode:** Sync
- **Exposed By:** Web (`DELETE /api/v1/projects/{id}/saved-tests/{id}`), MCP (`delete_saved_test` with `confirm=True`)

### UC-08: Localize Regression Failure (`analyze_failure`)
- **Summary:** Correlates failure evidence (console, network, selector, route, screenshot) against commit diff and repository AST to produce ranked suspect files.
- **Service Method:** `kawach.services.LocalizationService.localize_failure`
- **Inputs:** `scope: Scope`, `project_id: str`, `commit_sha: str`, `run_id: str`, `test_id: str`
- **Outputs:** `FailureAnalysisRead` (`suspectFiles[{path, lineRange, confidence, reason}]`, `explanation`)
- **Execution Mode:** Sync / Async
- **Exposed By:** Web (`GET /api/v1/projects/{id}/commits/{sha}/analysis`), GitHub (PR comments), MCP (`get_failure_analysis`)

### UC-09: Suggest Minimal Defect Patch (`suggest_fix`)
- **Summary:** Generates a unified git diff targeting the highest-confidence localized culprit file within policy limits (&le; 1 file, &le; 20 lines).
- **Service Method:** `kawach.services.FixService.suggest_fix`
- **Inputs:** `scope: Scope`, `project_id: str`, `commit_sha: str`, `analysis_id: str`
- **Outputs:** `FixSuggestionRead` (`diff`, `target_file`, `lines_changed`, `risk_class`, `is_small_fix`)
- **Execution Mode:** Sync / Async
- **Exposed By:** Web (`POST /api/v1/projects/{id}/commits/{sha}/suggest-fix`), MCP (`suggest_fix`)

### UC-10: Deterministically Validate Fix (`validate_fix`)
- **Summary:** Applies proposed diff in a clean scratch clone, verifies target app boot, and replays failing script 3x plus full test suite.
- **Service Method:** `kawach.services.FixService.validate_fix`
- **Inputs:** `scope: Scope`, `project_id: str`, `commit_sha: str`, `fix_id: str`
- **Outputs:** `FixValidationRead` (`status`: "validated" | "unvalidated", `replay_passed: bool`, `suite_passed_count: int`)
- **Execution Mode:** Async
- **Exposed By:** Web (`POST /api/v1/projects/{id}/commits/{sha}/validate-fix`), MCP (`apply_fix` with `confirm=True`)

### UC-11: Manage Scoped API Tokens (`manage_tokens`)
- **Summary:** Creates, lists, and revokes cryptographic API tokens for CLI and MCP clients. Tokens are hashed at rest via SHA-256.
- **Service Methods:**
  - `kawach.services.ApiTokenService.create_token`
  - `kawach.services.ApiTokenService.list_tokens`
  - `kawach.services.ApiTokenService.revoke_token`
- **Inputs:**
  - Create: `scope: Scope`, `name: str`, `scopes: List[str]`, `expires_in_days: Optional[int]`
  - List: `scope: Scope`
  - Revoke: `scope: Scope`, `token_id: str`
- **Outputs:**
  - Create: `ApiTokenCreated` (`id`, `name`, `token_prefix`, `token_secret` - returned once)
  - List: `List[ApiTokenRead]` (`id`, `name`, `token_prefix`, `scopes`, `last_used_at`, `created_at`)
  - Revoke: `SuccessResponse`
- **Execution Mode:** Sync
- **Exposed By:** Web (`/api/v1/auth/tokens`), CLI
