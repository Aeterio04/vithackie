# KAWACH — Agentic System & Multi-Client Architecture Audit

> **Audit Classification:** Architectural Baseline & Implementation Gap Analysis  
> **Status:** Current State Baseline Audit  
> **Scope:** Agentic Subsystems, Commit Loop, Auto-Fix Pipeline, and Three Front Doors (Web, GitHub, MCP)

---

## 1. Subsystem Component Audit Matrix

| Subsystem / Component | Current File Location | Status | Implementation Gaps & Needs |
|---|---|---|---|
| **Service Layer Core** | `kawach.services` | Partial / Scaffolding | Existing services (`auth`, `project`, `export`) are fragmented. Need unified use-case catalog (`docs/USE_CASES.md`) exposing `start_run`, `approve_catalog`, `run_regression`, `analyze_failure`, `suggest_fix`, `validate_fix`, `save_test` with `ApiClient` identity ("web", "github", "mcp") and idempotency keys. |
| **API Token Auth** | `kawach.db.models`, `kawach.api` | Missing | Need `ApiToken` SQLAlchemy model, repository, service methods (create, list, revoke, SHA-256 hash at rest), bearer/query dependency in `deps.py`, and token management endpoints (`/api/v1/auth/tokens`). |
| **Deep Explorer Agent** | `kawach.agents.explorer` | Real (Shallow BFS) | Current crawler performs simple URL discovery + single LLM summary. Needs state-graph exploration (DOM signature + UI state fingerprinting), L0–L3+ depth tracking, frontier priority queue, journeys extraction (depth &ge; 3), watchdog loop detection, and per-state signals (a11y, 4xx/5xx, broken links). |
| **Planner & Edge Engine** | `kawach.agents.planner` | Real (Single-Level) | Current planner generates flat catalog mapped to S1..Sn. Needs extended `TestCase` schema (`depth`, `preconditions`, `setup`, `steps[]`, `edgeTags[]`, `coverageRef`, `riskScore`), 4 test archetypes (single, journey, deep, edge), data-driven edge-case library, and coverage matrix. |
| **Test Runner & Verification** | `kawach.execution.runner`, `verifier` | Real (Core active) | Test runner executes Playwright tests and verifier performs 3x replays. Needs per-step assertions & evidence, checkpoint-based reporting, shared state reset between workers, and active exploratory tester mutating journeys from deepest unexplored states with reproduction path shrinking. |
| **Saved Test Library** | `kawach.services.saved_tests`, `api.v1.saved_tests` | Scaffold (501 / NIE) | Schemas and DB models exist (`SavedTest`, `SavedTestCoverage`). Routes return 501. Needs real `SavedTestService`, CRUD routes, SHA-256 script artifact storage, and diff-aware test selection mapping. |
| **Commit Regression Loop** | `kawach.workflows.regression`, `api.v1.commits` | Scaffold (501 / Skeleton) | LangGraph regression graph has 6 dummy nodes. Routes return 501. Needs real implementations for `select_tests`, `run_saved`, `verify`, `localize`, `suggest_fix`, `validate_fix`, commit event ingestion (web, webhook, simulate-commit), and GitHub summary reporting. |
| **Localization Agent** | `kawach.agents.localizer` | Scaffold (Protocol) | `LocalizerAgentProtocol` defined. Needs real agent implementation with candidate file retrieval prior to LLM call, ranking `suspectFiles[{path, lineRange, confidence, reason}]`, and fake-LLM fixtures. |
| **Fix Suggester & Validator** | `kawach.agents.fix_suggest`, `services.fix_service` | Scaffold (Protocol) | `FixSuggesterAgentProtocol` defined. Needs real unified diff generation, `validate_fix` scratch repo replay runner with 3x verification, safety classification (`is_small_fix`, `is_fix_allowed`), and optional PR opening. |
| **Web Client Dashboard** | `apps/web/src/features` | Partial (Empty States) | Core run cockpit is functional. `library/` and `commits/` features are placeholder empty states. Needs saved test manager, commit regression history, failure analysis drawer, and API-token settings page. |
| **GitHub Webhook Adapter** | `kawach.api.v1.webhooks` | Scaffold (Active HMAC) | HMAC-SHA256 signature verification and idempotency checks are active, but endpoint returns 501. Needs connection to commit regression use-case. |
| **MCP Server Adapter** | `apps/mcp` | Missing | Directory and server do not exist. Needs thin stdio MCP server calling backend service use-cases with API token auth, read-only default tools, explicit confirmation for write actions, and structured artifact output. |
| **Commit Benchmarks** | `benchmarks/commit-cases` | Missing | Needs 3+ prepared bad commits with known culprit files and scoring script computing top-1/top-3 localization accuracy. |

---

## 2. Invariant & Architecture Compliance Review

1. **Layered Unidirectional Flow:**
   - Existing 5 import-linter contracts are fully preserved. Agents never import `api` or `services`. Workflows never import `api`.
2. **Three Front Doors Architecture:**
   - Business logic must reside strictly inside `kawach.services`. Web routes, GitHub webhooks, and the MCP server are thin adapters translating input and invoking service use-cases.
3. **Security & Sandboxing:**
   - Untrusted repository and DOM content are enclosed in `<untrusted_content>` tags.
   - API tokens are hashed at rest (SHA-256). Passwords and tokens never appear in logs, prompts, or tool schemas.
4. **Zero Flakiness Verification:**
   - Defect confirmation and fix validation require 3x clean replay verification through `kawach.execution.verifier`. No LLM decides defect veracity.
