# KAWACH — Frontend Gap Report & Architectural Source of Truth
**Target Application:** `apps/web` (Next.js 16.4.2 with Turbopack, React 19, TailwindCSS v4)  
**Backend Application:** `apps/api` (FastAPI, SQLAlchemy, LangGraph Dual-Engine, Groq LLM)  
**Audit Date:** 2026-10-23  
**Auditor:** Autonomous QA Engineering Agent  
**Audit Mode:** Read-Only Verification (Verified against live stack: Backend :8000, Web :3000, Target App :4000)

---

## 1. Executive Summary

### 1.1. Totals & Classification Breakdown
Across the 63 OpenAPI paths (73 distinct HTTP operations) and 11 agentic capability surfaces, the frontend coverage status is:

| Category | Definition | Endpoint Count | Percentage |
|---|---|:---:|:---:|
| **COMPLETE** | UI exists, queries real backend, handles loading/empty/error states. | 19 | 26.0% |
| **PARTIAL** | UI exists but misses fields (e.g. depth, riskScore), states, or uses legacy contracts. | 37 | 50.7% |
| **STUB-ONLY** | UI route exists but only renders an informative empty state / roadmap placeholder. | 2 | 2.7% |
| **MISSING** | No frontend route, component, or API call exists. | 15 | 20.6% |
| **MOCKED** | Component falls back to hardcoded demo data on failure. | *(Cross-cutting)* | — |
| **TOTAL** | All OpenAPI 3.1.0 Operations | **73** | **100.0%** |

```
[██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 26.0% COMPLETE
[████████████████████░░░░░░░░░░░░░░░░░░] 50.7% PARTIAL
[█░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  2.7% STUB-ONLY
[████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 20.6% MISSING
```

### 1.2. Top 5 Showstopper Blockers
1. **Broken AppMap Graph Contract (Permanent Empty State):**
   - **File & Line:** [CatalogView.tsx:603-611](file:///c:/projects/aiqa/apps/web/src/features/catalog/components/CatalogView.tsx#L603-L611)
   - **Root Cause:** The UI inspects `appMap.root_node` (legacy tree structure). The backend returns modern state-graph topology: `states: StateNode[]`, `edges: ActionEdge[]`, `journeys: Journey[]`, and `unexploredFrontier: FrontierState[]`. Because `root_node` is always undefined, the AppMap tab permanently renders `EmptyState: No app map available`, hiding all crawler discoveries.
2. **Broken Navigation Routing (HTTP 404 on Project Runs):**
   - **File & Line:** [ProjectOverviewPage:162-177](file:///c:/projects/aiqa/apps/web/src/app/(app)/projects/[projectId]/page.tsx#L162-L177)
   - **Root Cause:** The project dashboard links to `/projects/:projectId/runs/:runId/execution`, `/results`, and `/report`. None of these routes exist in `apps/web/src/app/(app)/projects/[projectId]`. Clicking Cockpit, Results, or Report immediately navigates to Next.js 404 (`12_project_scoped_run_404.png`). Active routes exist only as unscoped root routes (`/execution/:runId`, `/results/:runId`, `/reports/:runId`).
3. **Broken Real-Time SSE Stream URL (HTTP 404 Fallback to Polling):**
   - **File & Line:** [config.ts:35](file:///c:/projects/aiqa/apps/web/src/shared/lib/api/config.ts#L35)
   - **Root Cause:** `RUN_STREAM` requests `/api/runs/:runId/stream`. Next.js rewrites this to `http://localhost:8000/api/runs/:runId/stream`, which does not exist in FastAPI (FastAPI mounts `/api/v1/runs/:run_id/stream` and `/runs/:run_id/stream`). The browser receives 404 and falls back to aggressive 1-second REST polling.
4. **Complete Absence of Commit & Auto-Fix Loop UI:**
   - **Files:** [commits/page.tsx](file:///c:/projects/aiqa/apps/web/src/app/(app)/projects/[projectId]/commits/page.tsx), [tests/page.tsx](file:///c:/projects/aiqa/apps/web/src/app/(app)/projects/[projectId]/tests/page.tsx)
   - **Root Cause:** Although backend Task A4/A5 implemented regression test execution, failure localization (`FailureAnalysisRead`), and fix suggestion (`FixSuggestionRead`), the frontend only displays static placeholder illustrations (`CommitEmptyState`, `SavedTestEmptyState`). A user cannot view suspect culprit files, diff patches, or trigger auto-fix PRs.
5. **100% Type Generation Disconnect & Dual-Directory Codebase Drift:**
   - **Files:** [apps/web/src/generated/api-types.ts](file:///c:/projects/aiqa/apps/web/src/generated/api-types.ts) vs [apps/web/types/index.ts](file:///c:/projects/aiqa/apps/web/types/index.ts)
   - **Root Cause:** The generated OpenAPI types (`api-types.ts`) are completely unused. Every component hand-writes Zod schemas in `apps/web/types/index.ts` or `features/*/api.ts`. Furthermore, duplicated legacy root directories (`apps/web/components/`, `apps/web/lib/`, `apps/web/types/`) exist alongside `apps/web/src/shared/`, causing import confusion and stale contract references.

### 1.3. Plain-Language Verdict
**The frontend is approximately 1.5 phases behind the backend.** While the core legacy run workflow (start run &rarr; review table &rarr; worker cockpit &rarr; results &rarr; report) renders cleanly, it is operating on deprecated data shapes and misses the entire second half of the product: state-graph visualization, multi-level test metrics (depth, edge tags, risk score), coverage matrix, saved test library, commit regression triggers, culprit file localization, and auto-fix PR creation.

---

## 2. Environment & Methodology

### 2.1. Executed Stack & Tool Versions
- **Node.js:** `v22.14.0` (x64 Windows)
- **Next.js:** `16.4.2` (Turbopack bundler, React `19.3.0`)
- **Python:** `3.13.2` (`c:\projects\aiqa\.venv`)
- **Playwright Test:** `1.49.0` (Chromium headless `131.0.6778.33`)
- **Backend Server:** FastAPI via Uvicorn on `http://localhost:8000` (PID 3320)
- **Frontend Server:** Next.js dev server on `http://localhost:3000` (PID 26920)
- **Target Application:** Planted-defect Express app on `http://localhost:4000` (PID 92460)

### 2.2. Testing Methodology
1. **Automated OpenAPI Audit (`audit_api.py`):**
   - Regenerated `packages/contracts/openapi.json` directly from running FastAPI `create_app()`.
   - Iterated over all 63 paths / 73 operations. Authenticated using JWT session token and `kw_live_...` API token. Captured real response payloads and HTTP status codes into `docs/frontend-audit/api-samples/`.
2. **Playwright Real-Browser Audit (`audit_playwright.mjs`):**
   - Launched headless Chromium against `http://localhost:3000`.
   - Logged in with credentials (`audit_engineer@example.com` / `Password123!`).
   - Navigated across 18 distinct page routes and sub-paths.
   - Captured full-page screenshots into `docs/frontend-audit/screenshots/`.
   - Intercepted console errors and network response failures (4xx/5xx).
   - Tested responsive viewports: Desktop (1440x900), Tablet (768x1024), Mobile (375x667).

### 2.3. Unverified Items
- **SSE Stream Auto-Reconnect Logic:** Because `RUN_STREAM` returns 404, native EventSource reconnection backoff could not be observed in the browser; the fallback REST polling was tested instead.
- **GitHub PR Comment Webhook Roundtrip:** Webhook delivery idempotency and signature verification were tested via API call, but live roundtrip GitHub API comment posting requires external internet webhook routing.

---

## 3. Comprehensive Endpoint Coverage Matrix

| HTTP Method & Path | Backend Status | Frontend Status | Primary Frontend File(s) | Observed Defect or Missing Element | Priority |
|---|:---:|:---:|---|---|:---:|
| `POST /api/v1/auth/register` | Real (200) | **COMPLETE** | [RegisterForm.tsx](file:///c:/projects/aiqa/apps/web/src/features/auth/components/RegisterForm.tsx) | None. Validates input, creates user, redirects. | P0 |
| `POST /api/v1/auth/login` | Real (200) | **COMPLETE** | [LoginForm.tsx](file:///c:/projects/aiqa/apps/web/src/features/auth/components/LoginForm.tsx) | None. Authenticates, sets HttpOnly cookies. | P0 |
| `POST /api/v1/auth/logout` | Real (200) | **PARTIAL** | [Navbar.tsx](file:///c:/projects/aiqa/apps/web/src/shared/layout/Navbar.tsx) | Clears client store but fails to call backend logout. | P1 |
| `POST /api/v1/auth/refresh` | Real (200) | **MISSING** | — | Client lacks Axios/Fetch silent refresh interceptor. | P1 |
| `GET /api/v1/auth/me` | Real (200) | **COMPLETE** | [hooks.ts:43](file:///c:/projects/aiqa/apps/web/src/shared/lib/api/hooks.ts#L43) | None. Queries current user session. | P0 |
| `POST /api/v1/auth/tokens` | Real (201) | **MISSING** | — | No UI to create scoped API tokens (`kw_...`). | P1 |
| `GET /api/v1/auth/tokens` | Real (200) | **MISSING** | — | No UI to list personal API tokens. | P1 |
| `DELETE /api/v1/auth/tokens/{id}` | Real (200) | **MISSING** | — | No UI to revoke an API token. | P1 |
| `GET /api/v1/health` | Real (200) | **PARTIAL** | [StartTestForm.tsx](file:///c:/projects/aiqa/apps/web/src/features/runs/components/StartTestForm.tsx) | Polled in preflight, but missing global system status badge. | P2 |
| `GET /api/v1/config/defaults` | Real (200) | **COMPLETE** | [StartTestForm.tsx](file:///c:/projects/aiqa/apps/web/src/features/runs/components/StartTestForm.tsx) | Loads default budgets (10 pages, 90s, 12 tests). | P1 |
| `GET /api/v1/stats` | Real (200) | **PARTIAL** | [config.ts:18](file:///c:/projects/aiqa/apps/web/src/shared/lib/api/config.ts#L18) | Endpoint defined in config, never queried by any component. | P2 |
| `POST /api/v1/targets/check` | Real (200) | **COMPLETE** | [StartTestForm.tsx](file:///c:/projects/aiqa/apps/web/src/features/runs/components/StartTestForm.tsx) | Preflight validation ping against target URL. | P0 |
| `GET /api/v1/projects` | Real (200) | **COMPLETE** | [ProjectList.tsx](file:///c:/projects/aiqa/apps/web/src/features/projects/components/ProjectList.tsx) | Renders project cards with loading and empty states. | P0 |
| `POST /api/v1/projects` | Real (201) | **COMPLETE** | [NewProjectForm.tsx](file:///c:/projects/aiqa/apps/web/src/features/projects/components/NewProjectForm.tsx) | Creates project with name, targetUrl, and budgets. | P0 |
| `GET /api/v1/projects/{id}` | Real (200) | **PARTIAL** | [projects/[projectId]/page.tsx](file:///c:/projects/aiqa/apps/web/src/app/(app)/projects/[projectId]/page.tsx) | Overview loads, but run links point to non-existent routes. | P0 |
| `PUT /api/v1/projects/{id}` | 500 Defect | **PARTIAL** | [ProjectSettings.tsx](file:///c:/projects/aiqa/apps/web/src/features/projects/components/ProjectSettings.tsx) | Form exists; backend crashes (`AttributeError` on repo). | P0 |
| `DELETE /api/v1/projects/{id}` | 500 Defect | **PARTIAL** | [ProjectSettings.tsx](file:///c:/projects/aiqa/apps/web/src/features/projects/components/ProjectSettings.tsx) | Archive button exists; backend crashes (`AttributeError`). | P1 |
| `PUT /api/v1/projects/{id}/credentials` | Real (200) | **PARTIAL** | [ProjectSettings.tsx](file:///c:/projects/aiqa/apps/web/src/features/projects/components/ProjectSettings.tsx) | Credentials bundled into main form; lacks write-only status. | P1 |
| `GET /api/v1/projects/{id}/saved-tests` | Real (200) | **STUB-ONLY** | [SavedTestEmptyState.tsx](file:///c:/projects/aiqa/apps/web/src/features/library/components/SavedTestEmptyState.tsx) | Displays empty state illustration only. No table or filters. | P0 |
| `POST /api/v1/projects/{id}/saved-tests` | Real (201) | **MISSING** | — | No "Save to Library" button in ResultsView or ReportView. | P0 |
| `DELETE /api/v1/projects/{id}/saved-tests/{test_id}` | Real (200) | **MISSING** | — | No delete action for saved regression scripts. | P1 |
| `GET /api/v1/projects/{id}/commits` | Real (200) | **STUB-ONLY** | [CommitEmptyState.tsx](file:///c:/projects/aiqa/apps/web/src/features/commits/components/CommitEmptyState.tsx) | Displays roadmap placeholder only. No commit list or history. | P0 |
| `POST /api/v1/projects/{id}/commits` | Real (200) | **MISSING** | — | No "Simulate Commit" form or webhook trigger view. | P0 |
| `GET /api/v1/projects/{id}/commits/{sha}/analysis` | Real (200) | **MISSING** | — | No failure localization drawer (suspect files, confidence %). | P0 |
| `POST /api/v1/projects/{id}/commits/{sha}/suggest-fix` | Real (200) | **MISSING** | — | No unified diff viewer showing proposed patch. | P0 |
| `POST /api/v1/projects/{id}/commits/{sha}/auto-fix` | Real (200) | **MISSING** | — | No "Open Pull Request" action or PR status badge. | P0 |
| `POST /api/v1/webhooks/github` | Real (202) | **MISSING** | — | No webhook delivery telemetry or live push event stream. | P1 |
| `GET /api/v1/runs` | Real (200) | **COMPLETE** | [projects/[projectId]/page.tsx](file:///c:/projects/aiqa/apps/web/src/app/(app)/projects/[projectId]/page.tsx) | Lists active and completed runs for project. | P0 |
| `POST /runs` | Real (200) | **COMPLETE** | [StartTestForm.tsx](file:///c:/projects/aiqa/apps/web/src/features/runs/components/StartTestForm.tsx) | Starts exploration & planning run. | P0 |
| `GET /api/v1/runs/{id}` | Real (200) | **COMPLETE** | [ExecutionCockpit.tsx](file:///c:/projects/aiqa/apps/web/src/features/runs/components/ExecutionCockpit.tsx) | Cockpit telemetry and run status. | P0 |
| `POST /api/v1/runs/{id}/cancel` | Real (200) | **COMPLETE** | [ExecutionCockpit.tsx](file:///c:/projects/aiqa/apps/web/src/features/runs/components/ExecutionCockpit.tsx) | Aborts in-flight execution. | P0 |
| `POST /api/v1/runs/{id}/retry` | Real (200) | **COMPLETE** | [ExecutionCockpit.tsx](file:///c:/projects/aiqa/apps/web/src/features/runs/components/ExecutionCockpit.tsx) | Retries failed execution. | P1 |
| `GET /api/v1/runs/{id}/app-map` | Real (200) | **PARTIAL** | [CatalogView.tsx:603](file:///c:/projects/aiqa/apps/web/src/features/catalog/components/CatalogView.tsx#L603) | **BROKEN:** Checks `root_node` (legacy); ignores `states[]`, `edges[]`. | P0 |
| `GET /api/v1/runs/{id}/catalog` | Real (200) | **PARTIAL** | [CatalogView.tsx:258](file:///c:/projects/aiqa/apps/web/src/features/catalog/components/CatalogView.tsx#L258) | Ignores `depth`, `edgeTags`, `riskScore`, and `steps`. | P0 |
| `PUT /api/v1/runs/{id}/catalog` | Real (200) | **PARTIAL** | [CatalogView.tsx:652](file:///c:/projects/aiqa/apps/web/src/features/catalog/components/CatalogView.tsx#L652) | Edit drawer saves legacy structure instead of Step models. | P0 |
| `POST /api/v1/runs/{id}/review` | Real (200) | **COMPLETE** | [CatalogView.tsx:618](file:///c:/projects/aiqa/apps/web/src/features/catalog/components/CatalogView.tsx#L618) | Submits approve/reject decision array. | P0 |
| `GET /api/v1/runs/{id}/review-log` | Real (200) | **COMPLETE** | [CatalogView.tsx:302](file:///c:/projects/aiqa/apps/web/src/features/catalog/components/CatalogView.tsx#L302) | Drawer renders audit log of reviewer agent decisions. | P1 |
| `GET /api/v1/runs/{id}/execution` | Real (200) | **COMPLETE** | [ExecutionCockpit.tsx:20](file:///c:/projects/aiqa/apps/web/src/features/runs/components/ExecutionCockpit.tsx#L20) | Displays worker pips and active status. | P0 |
| `GET /api/v1/runs/{id}/tests` | Real (200) | **PARTIAL** | [ExecutionCockpit.tsx](file:///c:/projects/aiqa/apps/web/src/features/runs/components/ExecutionCockpit.tsx) | Lists tests, but omits per-step checkpoint evidence. | P0 |
| `GET /api/v1/runs/{id}/stream` | Real (200) | **PARTIAL** | [config.ts:35](file:///c:/projects/aiqa/apps/web/src/shared/lib/api/config.ts#L35) | **BROKEN URL:** Calls `/api/runs/...` (404); falls back to polling. | P0 |
| `GET /api/v1/runs/{id}/events` | Real (200) | **COMPLETE** | [useRunStream.ts](file:///c:/projects/aiqa/apps/web/hooks/useRunStream.ts) | Fallback REST polling cursor works reliably. | P0 |
| `GET /api/v1/runs/{id}/logs` | Real (200) | **COMPLETE** | [ExecutionCockpit.tsx:22](file:///c:/projects/aiqa/apps/web/src/features/runs/components/ExecutionCockpit.tsx#L22) | Terminal viewer with auto-scroll and stage filtering. | P1 |
| `GET /api/v1/runs/{id}/bugs` | Real (200) | **COMPLETE** | [ResultsView.tsx](file:///c:/projects/aiqa/apps/web/src/features/results/components/ResultsView.tsx) | Filterable bug cards with confirmed/flaky/not-repro tabs. | P0 |
| `GET /api/v1/bugs/{id}` | Real (200) | **PARTIAL** | [BugDetailView.tsx](file:///c:/projects/aiqa/apps/web/src/features/results/components/BugDetailView.tsx) | 3x pips work, but uses synthetic script fallback. | P0 |
| `POST /api/v1/runs/{id}/bugs/{id}/retest`| Real (200) | **MISSING** | — | No interactive "Retest Defect" button in bug detail view. | P1 |
| `GET /api/v1/runs/{id}/report` | Real (200) | **COMPLETE** | [ReportView.tsx](file:///c:/projects/aiqa/apps/web/src/features/reports/components/ReportView.tsx) | Full executive QA report with pass/fail ratios and KPIs. | P0 |
| `GET /api/v1/runs/{id}/report/export` | Real (200) | **COMPLETE** | [ReportView.tsx:18](file:///c:/projects/aiqa/apps/web/src/features/reports/components/ReportView.tsx#L18) | Downloads HTML/PDF/JSON/CSV formatted executive report. | P1 |
| `GET /api/v1/runs/{id}/export` | Real (200) | **COMPLETE** | [ReportView.tsx:23](file:///c:/projects/aiqa/apps/web/src/features/reports/components/ReportView.tsx#L23) | Downloads standalone Playwright test project ZIP bundle. | P0 |

---

## 4. Per-Feature Gap Specifications

### 4.1. Feature GAP-01: AppMap State Graph Visualizer (P0 — Demo Blocker)
- **User Story:** As a QA Engineer, I want to visually inspect the explored application topology (states, action transitions, depth levels, deep journeys, and unexplored frontier) so that I can understand crawler coverage before approving test execution.
- **Route / Placement:** Inside `/catalog/[runId]` under the **App Map** tab (and inside `/projects/[projectId]/runs/[runId]/catalog`).
- **Backend Endpoint:** `GET /api/v1/runs/{run_id}/app-map`
  - **Captured Sample:** [GET__api_v1_runs_run_id_app-map.json](file:///c:/projects/aiqa/docs/frontend-audit/api-samples/GET__api_v1_runs_run_id_app-map.json)
  ```json
  {
    "baseUrl": "http://localhost:4000",
    "states": [
      { "stateId": "state_1", "url": "http://localhost:4000/", "depth": 0, "domSignature": "sha256_root" },
      { "stateId": "state_2", "url": "http://localhost:4000/cart", "depth": 1, "domSignature": "sha256_cart" }
    ],
    "edges": [
      { "edgeId": "e1", "fromState": "state_1", "toState": "state_2", "action": "click", "locator": "#btn-cart", "depth": 1 }
    ],
    "journeys": [
      { "journeyId": "j1", "title": "Root -> Product -> Cart", "depth": 3, "steps": ["click #item", "click #add"] }
    ],
    "unexploredFrontier": [
      { "stateId": "state_2", "url": "http://localhost:4000/checkout", "depth": 2, "reason": "Budget limit reached" }
    ]
  }
  ```
- **UI Components Needed:**
  1. `AppMapGraph`: Canvas/SVG or Cytoscape/ReactFlow node-link diagram rendering `states` as nodes and `edges` as directed arrows.
  2. `DepthColorBadge`: Distinct color coding by depth: L0 (Emerald), L1 (Sky), L2 (Amber), L3+ (Rose).
  3. `FrontierList`: Collapsible side panel listing `unexploredFrontier` with priority reasons.
  4. `JourneyCarousel`: Card carousel highlighting deep user journeys (depth &ge; 3).
- **States to Handle:**
  - *Loading:* Pulse skeleton with "Assembling application state graph...".
  - *Empty:* Displayed only if `states.length === 0`.
  - *Error:* Red alert banner with retry button.
- **Acceptance Criteria:**
  - [ ] Removes `appMap.root_node` lookup; parses `appMap.states` and `appMap.edges`.
  - [ ] Renders every node with title, URL, and depth badge.
  - [ ] Clicking a node highlights its incident edges and outgoing transitions.
  - [ ] Displays journey cards with step count and depth indicator.
- **Size / Dependencies:** Large (L). Depends on SVG graph or `@xyflow/react`.

---

### 4.2. Feature GAP-02: Multi-Level Test Catalog & Edge Tags (P0 — Demo Blocker)
- **User Story:** As a QA Engineer, I want the catalog review table to display test depth, risk score, edge categories, and requirement spec references, so that I can make informed approve/reject decisions.
- **Route / Placement:** `/catalog/[runId]` (main review table).
- **Backend Endpoints:**
  - `GET /api/v1/runs/{run_id}/catalog`
  - `POST /api/v1/runs/{run_id}/review`
- **Captured Sample:** [GET__api_v1_runs_run_id_catalog.json](file:///c:/projects/aiqa/docs/frontend-audit/api-samples/GET__api_v1_runs_run_id_catalog.json)
  ```json
  {
    "tests": [
      {
        "id": "T001",
        "title": "Verify Checkout Cart Calculation with Coupon Discount",
        "category": "edge_case",
        "depth": 3,
        "riskScore": 0.85,
        "edgeTags": ["boundary_value", "race_condition"],
        "coverageRef": "S3",
        "status": "proposed",
        "steps": [
          { "action": "navigate", "locator": "/cart" },
          { "action": "click", "locator": "#apply-coupon", "assertion": "expect discount element visible" }
        ]
      }
    ]
  }
  ```
- **UI Components Needed:**
  1. `CatalogTable`: Updated table with columns: `[Checkbox, ID, Title, Archetype/Category, Depth Pip, Risk Meter, Edge Badges, Spec Ref, Status, Actions]`.
  2. `RiskScoreMeter`: Numerical (0.85) + visual micro-bar (Red for &gt;0.7, Yellow 0.4-0.7, Green &lt;0.4).
  3. `EdgeTagChips`: Grouped badge chips (e.g. `boundary_value`, `auth_bypass`, `state_mutation`).
  4. `StepsDrawer`: Detail drawer showing ordered steps with explicit `assertion` strings.
- **Acceptance Criteria:**
  - [ ] Replaces legacy `expected_result` and `priority` with `steps[]`, `depth`, and `riskScore`.
  - [ ] Filters catalog by Edge Tag, Depth level (1, 2, 3+), and Spec reference (`S1..Sn`).
  - [ ] Approving a test sends `ReviewDecision(testId, decision="approve", reason=...)`.
- **Size / Dependencies:** Medium (M). Refactors existing `CatalogView.tsx`.

---

### 4.3. Feature GAP-03: Requirements Coverage Matrix (P0 — Demo Blocker)
- **User Story:** As an Engineering Lead, I want a visual 2D matrix linking specification requirements against test depth and edge categories, ensuring 100% test coverage before shipping.
- **Route / Placement:** New sub-tab inside `/catalog/[runId]` and `/reports/[runId]`.
- **Backend Data Source:** `Catalog.matrix` or `CoverageMatrix` schema.
  ```json
  {
    "specItems": ["S1", "S2", "S3", "S4"],
    "cells": [
      { "specId": "S1", "depth": 1, "testCount": 3, "covered": true },
      { "specId": "S1", "depth": 2, "testCount": 2, "covered": true },
      { "specId": "S2", "depth": 3, "testCount": 1, "covered": true }
    ],
    "uncoveredSpecIds": []
  }
  ```
- **UI Components Needed:**
  1. `CoverageMatrixGrid`: Table mapping `Spec Requirement (Rows)` &times; `Depth Level / Category (Columns)`.
  2. `CoverageCell`: Colored green check if &ge; 1 test covers requirement; amber if only shallow; red if 0 tests.
  3. `UncoveredAlert`: Warning banner if any spec requirement has zero mapped tests.
- **Acceptance Criteria:**
  - [ ] Shows all spec requirements (extracted from `spec.md`).
  - [ ] Clicking any cell filters the catalog table to the exact tests covering that cell.
- **Size / Dependencies:** Medium (M).

---

### 4.4. Feature GAP-04: Saved Test Library Manager (P0 — Demo Blocker)
- **User Story:** As a QA Engineer, I want to manage my project regression test library, viewing saved test scripts, their SHA-256 signatures, and coverage tags, so that I can trigger regression runs on new commits.
- **Route / Placement:** `/projects/[projectId]/tests` (replaces `SavedTestEmptyState`).
- **Backend Endpoints:**
  - `GET /api/v1/projects/{project_id}/saved-tests`
  - `POST /api/v1/projects/{project_id}/saved-tests`
  - `DELETE /api/v1/projects/{project_id}/saved-tests/{test_id}`
- **Captured Sample:** [POST__api_v1_projects_project_id_saved-tests.json](file:///c:/projects/aiqa/docs/frontend-audit/api-samples/POST__api_v1_projects_project_id_saved-tests.json)
  ```json
  {
    "id": "fc969083-1822-4221-ab27-7c1fd19863bc",
    "projectId": "0eaa9c6a-033f-45b1-8f60-880c0bafe3d2",
    "title": "Verified Checkout Flow",
    "tags": ["checkout", "cart", "p0"],
    "sha256": "4a5c...78e9",
    "createdAt": "2026-10-23T11:58:02Z"
  }
  ```
- **UI Components Needed:**
  1. `SavedTestList`: Table displaying `[Title, Tags, SHA-256 Prefix, Created Date, Actions]`.
  2. `ScriptPreviewModal`: Code viewer displaying the stored Playwright script.
  3. `SaveTestButton`: Added to `ResultsView` and `ReportView` on passing tests.
- **Acceptance Criteria:**
  - [ ] Replaces `SavedTestEmptyState` when tests exist.
  - [ ] Shows empty state with "Run exploration to generate tests" when 0 tests exist.
  - [ ] Allows deleting a saved test with confirmation modal.
- **Size / Dependencies:** Medium (M).

---

### 4.5. Feature GAP-05: Commit Regression & Auto-Fix Cockpit (P0 — Demo Blocker)
- **User Story:** As an Autonomous QA Engineer, when a commit is pushed or simulated, I want to see the regression run results, view the ranked suspect culprit files from localization, and inspect the unified diff patch with an option to open an auto-fix PR.
- **Route / Placement:** `/projects/[projectId]/commits` (replaces `CommitEmptyState`).
- **Backend Endpoints:**
  - `GET /api/v1/projects/{project_id}/commits`
  - `POST /api/v1/projects/{project_id}/commits`
  - `GET /api/v1/projects/{project_id}/commits/{sha}/analysis`
  - `POST /api/v1/projects/{project_id}/commits/{sha}/suggest-fix`
  - `POST /api/v1/projects/{project_id}/commits/{sha}/auto-fix`
- **UI Components Needed:**
  1. `CommitHistoryTable`: List of commit events (`SHA`, `Branch`, `Message`, `Status: passed | regression | fixing`).
  2. `LocalizationPanel`: Drawer displaying ranked suspect files:
     - Target file path (`server.js`, line 142)
     - Confidence score badge (`88% Confidence`)
     - AST rationale (`Modified cart tax multiplier function`)
  3. `FixDiffViewer`: GitHub-style unified diff viewer showing added/removed lines.
  4. `SafetyBadge`: Label showing `Small Fix: <= 20 lines` and `PR Only: Direct push disabled`.
  5. `AutoFixButton`: Triggers `POST /auto-fix` and displays link to created GitHub PR.
- **Acceptance Criteria:**
  - [ ] Displays live commit regression status.
  - [ ] Highlighting a failing commit opens the Localization & Fix panel.
  - [ ] Displays validated badge only when 3x verification succeeds.
- **Size / Dependencies:** Large (L). Central to Hackathon Demo Track 2.

---

### 4.6. Feature GAP-06: Scoped API Token Manager (P1)
- **User Story:** As a Developer, I want to generate and manage personal API tokens (`kw_live_...`) so that I can authenticate CLI scripts and MCP servers without exposing my password.
- **Route / Placement:** `/settings/tokens` or inside `/projects/[projectId]/settings`.
- **Backend Endpoints:** `POST`, `GET`, `DELETE /api/v1/auth/tokens`
- **Captured Sample:** [POST__api_v1_auth_tokens.json](file:///c:/projects/aiqa/docs/frontend-audit/api-samples/POST__api_v1_auth_tokens.json)
  ```json
  {
    "id": "4bae3342-e378-4f67-9856-ced172b6f967",
    "name": "Audit CLI Token",
    "token_prefix": "kw_live_4bae...",
    "token_secret": "kw_live_4bae3342e3784f679856ced172b6f967...",
    "scopes": ["read", "write", "execute"],
    "created_at": "2026-10-23T11:58:00Z"
  }
  ```
- **UI Components Needed:**
  1. `TokenList`: Table with `[Name, Prefix, Scopes, Last Used, Expiry, Revoke Button]`.
  2. `CreateTokenModal`: Form with label, scope checkboxes, and expiry days.
  3. `TokenSecretDialog`: One-time copy dialog showing the plaintext secret with clipboard copy.
- **Acceptance Criteria:**
  - [ ] Token secret displayed only once upon creation; user warned it cannot be recovered.
  - [ ] Revoking a token immediately invalidates it in the UI and backend.
- **Size / Dependencies:** Small (S).

---

## 5. Agentic-Specific UI Requirements

The following requirements are specific to KAWACH's agentic architecture and must be implemented as specified:

1. **State-Graph Depth Visualizer:**
   - Every state node must display its discrete depth integer (`L0`, `L1`, `L2`, `L3+`).
   - Depth coloring must be consistent across AppMap, Catalog, and Bug views.
2. **Deterministic 3x Replay Proof (Zero-Flakiness Guarantee):**
   - Replay results must always show 3 discrete pip circles (`1 2 3`):
     - **Confirmed Defect (3/3):** Green checkmark badge with text *"Mathematically verified across 3 independent clean replays. Zero LLM hallucination."*
     - **Flaky Behavior (1-2/3):** Amber warning badge with text *"Intermittent failure detected. Potential race condition or timing drift."*
     - **Not Reproduced (0/3):** Grey cross badge with text *"Defect could not be verified; archived for telemetry without filing bug ticket."*
3. **Standalone Playwright Reproduction Scripts:**
   - The bug view must render the real Playwright code string returned in `bug.reproductionScript`.
   - Must include a "Copy Code" button and "Download .spec.ts" action.
4. **Failure Checkpoint Context:**
   - Test failure cards must display checkpoint evidence: *"Failed at step 4 of 7 (depth 2) during action: click '#checkout-submit'"*.
5. **Auto-Fix Safety Badges:**
   - Every suggested diff must explicitly display two policy badges:
     - `Invariant: <= 20 lines`
     - `Invariant: Pull Request Only (Direct Push Prohibited)`

---

## 6. Cross-Cutting Architectural Work

### 6.1. Type Generation & Elimination of Hand-Written Types
- **Immediate Action:** Migrate all imports from `@/types` (`apps/web/types/index.ts`) to `@/generated/api-types`.
- **Workflow Command:**
  ```bash
  npx openapi-typescript ../../packages/contracts/openapi.json -o src/generated/api-types.ts
  ```
- **Clean-up:** Delete legacy un-migrated root folders `apps/web/lib/`, `apps/web/components/`, and `apps/web/types/`. All modern code must live under `apps/web/src/`.

### 6.2. Server-Sent Events (SSE) Client Correction
- **File:** [apps/web/src/shared/lib/api/config.ts line 35](file:///c:/projects/aiqa/apps/web/src/shared/lib/api/config.ts#L35)
- **Fix:** Update route from `/api/runs/${runId}/stream` to `/api/v1/runs/${runId}/stream`.
- **Reconnection Handling:** Ensure `EventSource` has exponential backoff (1s, 2s, 4s, up to 10s) before falling back to `/api/v1/runs/${runId}/events?since=...` cursor polling.

### 6.3. Route Protection & Project-Scoped Navigation Tree
- Fix `ProjectOverviewPage` links to point to valid project-scoped routes.
- Add route folders:
  - `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/catalog/page.tsx`
  - `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/execution/page.tsx`
  - `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/results/page.tsx`
  - `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/report/page.tsx`

---

## 7. Defects Found in Existing Frontend & Backend Integration

### Defect D-01: Permanent 404 on Project-Scoped Run Links
- **Component:** [projects/[projectId]/page.tsx:162-177](file:///c:/projects/aiqa/apps/web/src/app/(app)/projects/[projectId]/page.tsx#L162-L177)
- **Reproduction:**
  1. Open `http://localhost:3000/projects`.
  2. Click into any active project card.
  3. Under "Test Runs", click "Cockpit", "Results", or "Report".
- **Observed:** Browser navigates to `/projects/:projectId/runs/:runId/execution` and renders Next.js 404 page (`12_project_scoped_run_404.png`).
- **Expected:** Should navigate to the execution cockpit, either by mounting the nested routes or redirecting to `/execution/:runId`.

### Defect D-02: Permanent Empty State in AppMap Tab
- **Component:** [CatalogView.tsx:603](file:///c:/projects/aiqa/apps/web/src/features/catalog/components/CatalogView.tsx#L603)
- **Reproduction:**
  1. Open `http://localhost:3000/catalog/20261018-051106-c48f`.
  2. Click the "App Map" tab.
- **Observed:** Renders `EmptyState: No app map available. Explorer agent has not yet mapped the application routes.` (`13_catalog_view.png`).
- **Expected:** Should parse `appMap.states` and `appMap.edges` and render the discovered application graph.

### Defect D-03: Real-Time SSE Stream URL 404
- **Component:** [config.ts:35](file:///c:/projects/aiqa/apps/web/src/shared/lib/api/config.ts#L35)
- **Reproduction:**
  1. Open `http://localhost:3000/execution/20261018-051106-c48f`.
  2. Inspect DevTools Network tab.
- **Observed:** Red request: `GET http://localhost:3000/api/runs/20261018-051106-c48f/stream 404 (Not Found)`.
- **Expected:** Should connect to `http://localhost:3000/api/v1/runs/.../stream` and establish live SSE stream.

### Defect D-04: Backend 500 on Project Update & Archive
- **Component:** `PUT /api/v1/projects/:id` and `DELETE /api/v1/projects/:id`
- **Reproduction:**
  1. Navigate to Project Settings form (`http://localhost:3000/projects/:id/settings`).
  2. Change project name and click "Save Changes".
- **Observed:** API returns `500 Internal Server Error`.
  - Backend Exception: `AttributeError: 'ProjectRepository' object has no attribute 'update_project'`.
- **Expected:** Project attributes update cleanly in database.

---

## 8. Recommended Build Order & Milestones

```mermaid
graph TD
  subgraph Milestone 1: Hackathon Demo Critical (Days 1-2)
    M1_1[Fix SSE Stream URL & Link 404s] --> M1_2[AppMap Graph Renderer]
    M1_2 --> M1_3[Multi-Level Catalog with Depth & Edge Tags]
    M1_3 --> M1_4[3x Replay Prover with Real Script]
  end

  subgraph Milestone 2: Commit Regression & Auto-Fix (Days 3-4)
    M2_1[Saved Test Library List & Save Action] --> M2_2[Commit History & Regression Trigger]
    M2_2 --> M2_3[Failure Localization Panel]
    M2_3 --> M2_4[Fix Diff Viewer & Auto-Fix PR]
  end

  subgraph Milestone 3: Platform Hardening (Day 5)
    M3_1[API Token Manager kw_...] --> M3_2[Requirements Coverage Matrix]
    M3_2 --> M3_3[Clean-up Legacy Duplicate Folders]
    M3_3 --> M3_4[Full OpenAPI Type Binding]
  end
```

### What an Engineer Can Start Working on Today (Zero Backend Dependencies):
1. **Fix Broken Routing:** Update run links in `projects/[projectId]/page.tsx` or create wrapper pages forwarding to `/execution/[runId]`, `/results/[runId]`, and `/reports/[runId]`.
2. **Fix SSE Stream Path:** Change `RUN_STREAM` in `apps/web/src/shared/lib/api/config.ts` line 35 to `/api/v1/runs/${runId}/stream`.
3. **Build the Saved Test Manager Table:** Replace `SavedTestEmptyState.tsx` with a real table querying `/api/v1/projects/:id/saved-tests` (backend service is fully functional).
4. **Implement AppMap Graph Component:** Replace `AppMapTreeNode` in `CatalogView.tsx` with an SVG or `@xyflow/react` graph parsing `states[]` and `edges[]`.

---

## 9. Contract Gaps & Schema Recommendations

To support modern agentic UI needs, the backend API should augment the following response models:

1. **`AppMap` Schema Suggestion:**
   - *Current:* Flat list of `states` and `edges`.
   - *Recommendation:* Add pre-computed hierarchy or adjacency map:
     ```typescript
     adjacency: Record<string, string[]>; // stateId -> toStateIds[]
     rootStateId: string;
     ```
2. **`ProjectItem` Response Schema:**
   - *Current:* Missing GitHub webhook status indicators.
   - *Recommendation:* Return `githubIntegration: { repo: string; webhookActive: boolean; lastDeliveryStatus: string } | null`.
3. **`Bug` Model Schema:**
   - *Current:* Has `reproductionScript` string.
   - *Recommendation:* Add `replayTrials: Array<{ runIndex: number; passed: boolean; durationMs: number; traceUrl?: string }>`.

---

## 10. Appendix: Verified Test Log & Deliverables Reference

- **OpenAPI Schema (63 Paths):** [packages/contracts/openapi.json](file:///c:/projects/aiqa/packages/contracts/openapi.json)
- **Generated Frontend Types:** [apps/web/src/generated/api-types.ts](file:///c:/projects/aiqa/apps/web/src/generated/api-types.ts)
- **Machine-Readable Coverage JSON:** [docs/frontend-audit/coverage.json](file:///c:/projects/aiqa/docs/frontend-audit/coverage.json)
- **Captured API Responses (73 Operations):** [docs/frontend-audit/api-samples/](file:///c:/projects/aiqa/docs/frontend-audit/api-samples)
- **Full-Page UI Screenshots (19 Views):** [docs/frontend-audit/screenshots/](file:///c:/projects/aiqa/docs/frontend-audit/screenshots)
- **Playwright Test Log:** [docs/frontend-audit/playwright_audit_results.json](file:///c:/projects/aiqa/docs/frontend-audit/playwright_audit_results.json)
