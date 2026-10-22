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
| **Service Interface** | `kawach.services.regression_service` | Scaffold (501/NIE) | `RegressionServiceProtocol`, `RegressionService` |
| **Service Interface** | `kawach.services.localization_service` | Scaffold (501/NIE) | `LocalizationServiceProtocol`, `LocalizationService` |
| **Service Interface** | `kawach.services.fix_service` | Scaffold (501/NIE) | `FixServiceProtocol`, `FixService` |
| **Agent Interface** | `kawach.agents.localizer.interface` | Scaffold (NIE) | `LocalizerAgentProtocol`, `LocalizerAgent` |
| **Agent Interface** | `kawach.agents.fix_suggest.interface` | Scaffold (NIE) | `FixSuggesterAgentProtocol`, `FixSuggesterAgent` |
| **Workflow Graph** | `kawach.workflows.regression` | Scaffold / Tested | LangGraph state machine skeleton with 6 named nodes |
| **API Endpoints** | `kawach.api.v1.saved_tests` | Scaffold (501) | `GET/POST /projects/{id}/saved-tests`, `DELETE .../{test_id}` |
| **API Endpoints** | `kawach.api.v1.commits` | Scaffold (501) | `GET/POST /projects/{id}/commits`, `/analysis`, `/suggest-fix`, `/auto-fix` |
| **API Endpoints** | `kawach.api.v1.webhooks` | Scaffold (501) | `POST /api/v1/webhooks/github` (active HMAC check -> 501 response) |

---

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
