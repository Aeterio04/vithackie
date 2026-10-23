# Product Requirements Document (PRD) — KAWACH
## Autonomous AI Quality Assurance & Regression Defense Platform

> **Document Version:** 2.0.0  
> **Status:** Active / Production Baseline  
> **Classification:** Core Engineering & Product Specification  
> **Last Updated:** October 2026  
> **Target Audience:** Engineering, Product, QA Leads, Security Teams, and Agentic Integrators  

---

## 1. Executive Summary & Product Vision

### 1.1. Product Vision
**KAWACH** (the Hindi word for *Armour/Shield*) is an enterprise-grade Autonomous AI Quality Assurance platform designed to eliminate the manual overhead, cognitive drift, and flakiness inherent in modern web testing. 

Unlike traditional test generators that stop at generating fragile scripts or synthetic end-to-end tests from natural language prompts, KAWACH operates as an **unattended, closed-loop QA Engineer**. Given only a target application URL and a markdown functional specification (`spec.md`), KAWACH:
1. Explores deep interactive application topologies using an automated state-graph browser engine.
2. Formulates risk-prioritized, specification-linked test suites covering standard, deep, and edge-case journeys.
3. Synthesizes executable, production-grade Playwright TypeScript code with self-healing capabilities.
4. Executes tests in parallel, isolated browser sandboxes.
5. **Deterministically proves defects via 3x clean replay verification** (eliminating LLM hallucination).
6. Integrates directly into developer workflows via **Diff-Aware Commit Regression Testing**, **Probabilistic Culprit Localization**, and **Policy-Constrained Auto-Fix Pull Requests**.

### 1.2. Core Value Proposition
- **Zero Script Authoring Overhead:** No QA engineer needs to write boilerplate Playwright or Selenium code.
- **Zero False-Alarm Guarantee:** Defect confirmation requires mathematical $3/3$ deterministic replay proof against a clean application sandbox; no LLM is ever allowed to hallucinate or "judge" a bug's validity.
- **100% Traceable Spec Coverage:** Every single test case and discovered bug is linked back to explicit requirements ($S_1 \dots S_n$) in the functional specification.
- **Instant Regression Turnaround:** Instead of re-running the entire suite, commit webhooks trigger **diff-aware test selection**, matching changed source files against indexed coverage touchpoints to run targeted tests in seconds.
- **Three Unified Front Doors:** Every capability is natively accessible through a modern Next.js Web Dashboard, automated GitHub Actions/Webhooks, and an LLM-accessible Model Context Protocol (MCP) server.

---

## 2. Personas & Operational Modes

### 2.1. Target Personas
1. **Full-Stack / Frontend Engineers:** Wants instant regression feedback on every git push, exact line-level failure localization, and ready-to-merge small-fix pull requests.
2. **QA Directors & Test Leads:** Wants total requirement coverage visibility, automated edge-case fuzzing, exportable Playwright test suites, and audit-ready executive reports.
3. **Engineering Managers / VP Eng:** Wants reduced cycle times, high release velocity, zero escaped production bugs, and transparent token/execution budgets.
4. **Terminal / Autonomous Coding Agents:** LLMs operating in IDEs (Cursor, Antigravity, Claude Code) requiring structured MCP tools to trigger runs, query failures, and fetch diff suggestions.

### 2.2. Operational Modes

| Operational Mode | Trigger / Interface | Review Gate | Execution Flow | Primary Output |
| :--- | :--- | :--- | :--- | :--- |
| **Autonomous Mode** | UI Toggle / `mode="autonomous"` | Autonomous Reviewer Agent checks catalog against spec rules | Graph 1 seamlessly transitions to Graph 2 without user pause | Full test execution, verified bugs, and `report.md` |
| **Manual Mode** | UI Toggle / `mode="manual"` | Pauses at `awaiting_review`. Human inspects/edits catalog | Resumes upon explicit `POST /runs/{id}/execute` | Validated human-approved execution run |
| **Commit Regression Mode** | GitHub Push Webhook / PR | Automated diff-aware test selector | Runs only affected tests; localizes failure to culprit file | GitHub PR status comment, diff patch, and analysis |
| **Export Mode** | `GET /api/v1/runs/{id}/export` | N/A | Repackages verified passing tests with relative fixtures | Standalone, runnable Playwright test project (ZIP) |
| **Benchmark Mode** | CLI / Target App Suite | Automated comparison against `ground_truth.json` | Evaluates precision, recall, and replay stability | JSON benchmark scorecard (`benchmark.json`) |

---

## 3. High-Level Architecture & Multi-Client Topology

KAWACH is built on a layered, unidirectional architecture with three distinct front doors converging on a shared service layer, powered by a dual-graph agentic engine:

```
                            THE THREE FRONT DOORS
             +--------------------+--------------------+--------------------+
             |   Next.js 16 Web   |   GitHub Actions   |     MCP Server     |
             |     Dashboard      |     & Webhook      |    (apps/mcp)      |
             +---------+----------+---------+----------+---------+----------+
                       |                    |                    |
                       +--------------------+--------------------+
                                            |
                                            v
             +--------------------------------------------------------------+
             |                     FASTAPI CORE API LAYER                   |
             |   - Dual Auth: Web JWT Cookies vs. kw_live_ API Tokens       |
             |   - Scope Guard: runs:read/write, tests:read/write, etc.     |
             |   - Thread-Safe Idempotency-Key Cache (SHA-256)              |
             +------------------------------+-------------------------------+
                                            |
                       +--------------------+--------------------+
                       |                                         |
                       v                                         v
       +-------------------------------+         +-------------------------------+
       |      SERVICE DOMAIN LAYER     |         |     PERSISTENCE PLATFORM      |
       |  - TokenService & AuthService |         |  - Relational DB (SQLAlchemy) |
       |  - SavedTestService           | <=====> |  - Atomic Run Bundles (Disk)  |
       |  - RegressionService          |         |  - SHA-256 Artifact Vault     |
       |  - IdempotencyService         |         |  - Alembic Migration Engine   |
       +---------------+---------------+         +-------------------------------+
                       |
                       v
       +-----------------------------------------------------------------+
       |                  DUAL-GRAPH AGENTIC ENGINE                      |
       |                                                                 |
       |  [GRAPH 1: DISCOVERY & PLANNING]                                |
       |  Preflight -> State-Graph Explorer -> Planner -> Review Gate    |
       |                                                                 |
       |  [GRAPH 2: EXECUTION & REPAIR]                                  |
       |  Script Writer -> Runner -> Flake Gate -> 3x Verifier -> Report |
       +-----------------------------------------------------------------+
```

---

## 4. In-Depth Feature Specifications

---

### Feature 4.1: State-Graph Deep Exploration Engine (Task A2)

#### 4.1.1. Description
The exploration subsystem replaces traditional shallow link crawlers with an intelligent, state-machine-driven browser agent built on Chromium and Playwright. It systematically maps the interactive surface of an application, discovering deep modals, multi-step wizards, tab-switched views, and form validation frontiers.

#### 4.1.2. Key Capabilities & Technical Mechanics
1. **Deterministic State Fingerprinting:**
   - Every application state is hashed into an SHA-256 fingerprint:
     $$\text{StateHash} = \text{SHA-256}(\text{normalized\_url} + \text{dom\_tokens} + \text{ui\_state})$$
   - `dom_tokens`: Extracted structural representation of forms, inputs, buttons, headings, and dialogs.
   - `ui_state`: Active modal identifiers, selected tab indicators, and active form input states.
   - Transitions resulting in the same fingerprint are identified as no-ops or duplicates, preventing infinite exploration loops.
2. **Tiered Frontier Priority Queue:**
   - Frontier states are scheduled across 4 distinct depth tiers:
     - `L0`: Top-level navigational URLs and unauthenticated landing routes.
     - `L1`: Single-interaction states (clicking dropdowns, tabs, toggle switches).
     - `L2`: Multi-step flows (wizards, multi-field form sequences, search filters).
     - `L3+`: Deep paths (modals opened within wizards, nested menus, cross-feature state mutations).
3. **Fixed Action Set with Accessible Locators:**
   - Agents operate strictly through 8 discrete actions: `click`, `fill`, `select`, `press`, `navigate`, `back`, `refresh`, `wait`.
   - Element selection strictly prefers accessible role-based locators (`getByRole`, `getByText`, `getByLabel`) rather than fragile CSS/XPath selectors.
4. **Watchdog Loop & Oscillation Detection:**
   - Detects self-loops ($\ge 3$ consecutive actions returning to the identical state) and cyclic oscillations ($A \to B \to A \to B$).
   - Stalled branches are pruned, and the untraversed state is logged to `unexploredFrontier` with technical explanations.
5. **Per-State Signal Telemetry:**
   - Actively collects and attaches telemetry to every node:
     - Browser console errors and unhandled exceptions.
     - HTTP 4xx and 5xx responses.
     - Aborted or failed network fetches.
     - Structural accessibility violations (missing `alt` tags, unlabeled inputs, empty buttons).
6. **Automated Deep Journey Discovery:**
   - Traverses the discovered directed graph to identify acyclic paths of depth $\ge 3$, generating end-to-end user journeys for test planning.

---

### Feature 4.2: Multi-Level Test Planner & 14-Category Edge Engine (Task A3)

#### 4.2.1. Description
The planning engine transforms the application topology (`app_map.json`) and functional specification (`spec.md`) into an executable, risk-prioritized test catalog. It guarantees total requirement coverage while probing boundary edges and regression-prone UI vectors.

#### 4.2.2. Key Capabilities & Technical Mechanics
1. **The 4 Test Archetypes:**
   - **Single-Step Checks:** Direct assertions on specific UI elements or rendered content.
   - **Multi-Step Journeys:** Sequential workflows mapping directly to common user behaviors.
   - **Deep-Path Tests:** Chained screen transitions of depth $\ge 3$ where state carried from earlier steps directly impacts later steps.
   - **Data-Driven Edge Cases:** Fuzzing and boundary probing targeting specific failure modes.
2. **The 14-Category Edge-Case Library:**
   - Evaluates input and interaction boundaries across 14 systematic categories:
     1. *Empty / Whitespace Only*
     2. *Extreme String Length Boundaries* (> 255 chars, max int fields)
     3. *Unicode / Emoji / RTL Character Sets*
     4. *HTML / Script Injection Escaping* (`<script>alert(1)</script>`)
     5. *Negative Numbers & Boundary Values*
     6. *Duplicate Submissions*
     7. *Rapid Repeat Submit (Debounce & Double-Click Vulnerability)*
     8. *Browser History Navigation (Back / Forward / Refresh mid-flow)*
     9. *Interrupted Flows (Modal close, tab switch, navigation away)*
     10. *Session Expiration / Logout during active flow*
     11. *Order-of-Operations Permutations*
     12. *Keyboard-Only Navigation (Tab / Enter / Space without mouse)*
     13. *Viewport Resizing (Desktop vs. Mobile vs. Tablet layout drift)*
     14. *Network Failure & Offline Resilience*
3. **Prioritized Risk Scoring Formula:**
   $$\text{riskScore} = \text{spec\_criticality} \times \text{depth} \times \text{edge\_severity}$$
   - Tests are sorted descending by `riskScore` ($T_{01}, T_{02}, \dots$). If testing budgets or execution timeouts limit total run time, the highest-risk tests are guaranteed to execute first.
4. **3D Coverage Matrix:**
   - Constructs an explicit 3-dimensional mapping:
     $$\text{CoverageMatrix} = \text{SpecItems} \times \text{DepthLevels} (L0\dots L3+) \times \text{EdgeCategories}$$
   - Confirms 100% specification coverage with bidirectional links between test cases and requirements.
5. **Autonomous Reviewer Agent:**
   - In Autonomous Mode, the Reviewer agent verifies catalog completeness, checks step assertions, and logs explicit audit reasons for every approved test into `review_log.json`.

---

### Feature 4.3: Parallel Test Runner, Checkpoint Reporting & Self-Healing (Task A4)

#### 4.3.1. Description
The test execution engine runs synthesized Playwright TypeScript suites across sandboxed parallel browser workers. It isolates state between tests, provides granular step-level failure reporting, gates flakiness, and automatically repairs locator drift.

#### 4.3.2. Key Capabilities & Technical Mechanics
1. **Sandboxed Parallel Execution:**
   - Multi-worker execution (workers `w1`, `w2`) running isolated Playwright browser contexts.
   - Worker state reset fixtures clear all cookies, local storage, session storage, and permissions before and after every test, preventing cross-test pollution.
2. **Step-Level Checkpoint Telemetry:**
   - Hierarchically parses Playwright execution traces:
     - Identifies exact step index: `failedStep` ($k$ of $n$).
     - Identifies step depth and step checkpoint description.
     - Enables developers to pinpoint failures without re-running tests.
3. **Strict Flake Retry Gating (`is_infrastructure_flake`):**
   - Implements strict failure triage before retrying:
     - Network disconnections (`ECONNREFUSED`, `net::ERR_CONNECTION_REFUSED`), browser context crashes, and socket hangups are classified as infrastructure flakes and allowed 1 retry.
     - **Application assertion failures (`expect(...).toBe(...)`) are NEVER retried.** This prevents real bugs from being masked by arbitrary retries.
4. **1-Time Self-Healing Repair Loop:**
   - When a test fails due to locator timeouts, syntax errors, or minor DOM drift, the error trace and current DOM snapshot are passed back to the Script Writer agent for a single automated repair attempt before failure logging.

---

### Feature 4.4: Autonomous Exploratory Testing & Path Shrinking (Task A4)

#### 4.4.1. Description
Beyond pre-planned test cases, KAWACH features an active exploratory testing agent that launches dynamic mutations against the deepest unexplored frontier states of the application.

#### 4.4.2. Key Capabilities & Technical Mechanics
1. **Frontier Mutation Strategies:**
   - Launches exploratory tests ($X_{01}, X_{02}, \dots$) against high-depth unvisited states using 4 mutation tactics:
     - *Step Reordering*: Swapping non-dependent actions to uncover state dependencies.
     - *Mid-Flow Interruption*: Triggering modal dismissals or back actions during complex data entry.
     - *Rapid Submission*: Firing rapid concurrent events to stress debounce handlers.
     - *Payload Perturbation*: Swapping valid inputs with edge-case injection boundaries.
2. **Minimal Path Shrinking (`shrink_failing_path`):**
   - When an exploratory test uncovers a bug, the action sequence is often noisy. The path shrinking algorithm:
     - Discards all actions executed after the failure point.
     - Iteratively prunes non-essential intermediate actions.
     - Verifies whether the pruned path still reproduces the defect.
     - Outputs a minimal, clean Playwright reproduction script (`<bug_id>_repro.spec.ts`).

---

### Feature 4.5: Defect Triage & 100% Deterministic 3x Replay Verifier (Task A4)

#### 4.5.1. Description
Eliminates LLM hallucination and test flakiness from bug reporting. Every candidate bug undergoes automated triage, deduplication, and isolated 3x replay verification before being certified.

#### 4.5.2. Key Capabilities & Technical Mechanics
1. **Compound Signature Triage Deduplication:**
   - Failures are indexed by a compound signature:
     $$\text{DefectSignature} = \text{FailingStateID} \mathbin{::} \text{SymptomErrorSignature}$$
   - Distinct failure modes on different application views remain separate bugs.
   - Identical symptoms on the same screen (e.g., repeated form submission failures) are deduplicated into `bug.duplicates`, avoiding report bloat.
2. **Zero-LLM 3x Replay Verification:**
   - Candidate bugs are executed 3 consecutive times in an isolated browser runner:
     - The target application state is reset before each replay (`POST /__reset`).
     - **Replay Outcome Classification:**
       - **Confirmed (3/3):** Deterministically reproduces in all 3 runs. Certified as a genuine defect.
       - **Flaky (1/3 or 2/3):** Intermittent failure. Flagged as flaky with detailed timing and network logs.
       - **Not Reproduced (0/3):** Transient artifact. Dismissed from confirmed bug counts.
   - **Zero LLM Involvement:** An LLM is never permitted to "decide" whether a bug is real. Proof is strictly empirical.
3. **Comprehensive Evidence Packaging:**
   - Every confirmed bug includes:
     - Full-page failure screenshot (`screenshot.png`).
     - Video recording of the failing test run (`video.webm`).
     - Playwright execution trace archive (`trace.zip`).
     - Console error logs (`console.json`) and network request waterfall (`network.json`).
     - Standalone reproduction script (`<bug_id>_repro.spec.ts`).

---

### Feature 4.6: Diff-Aware Commit Regression Loop (Task A5)

#### 4.6.1. Description
KAWACH embeds directly into git push and pull request workflows. When a developer pushes new code, KAWACH inspects the diff, runs only the affected saved tests, and returns regression results in seconds.

#### 4.6.2. Key Capabilities & Technical Mechanics
1. **Saved Test Library (`SavedTestService`):**
   - High-value passing journeys and verified bug reproduction scripts are persisted to project test libraries.
   - Scripts are fingerprinted with SHA-256 hashes and saved under `data/artifacts/saved_tests/<project_id>/`.
   - Tests are tagged with coverage touchpoints: `page`, `route`, `component`, and functional `tags`.
2. **Diff-Aware Test Selection (`RegressionService`):**
   - Inspects the commit diff (using local `git diff` first, falling back to GitHub API).
   - Changed files (e.g., `apps/web/src/components/CheckoutModal.tsx`) are cross-referenced against indexed coverage touchpoints.
   - Schedules only the subset of tests covering the modified components.
   - **Safe Fallback:** If the diff is empty, touches global configurations, or matches no specific touchpoint, KAWACH safely runs the full saved test suite.
3. **LangGraph Regression Pipeline:**
   - Orchestrated via a compiled LangGraph state machine with 6 specialized nodes:
     `select_tests` $\to$ `run_saved` $\to$ `verify` $\to$ `localize` $\to$ `suggest_fix` $\to$ `validate_fix`.
4. **Canonical Workspace Depth Staging:**
   - Overcomes relative TypeScript import failures by dynamically staging scripts into canonical workspace locations (`runs/<run_id>/scripts/`) with automated fixture import path resolution before execution.

---

### Feature 4.7: Probabilistic Culprit Localization & Auto-Fix Pipeline (Task A6)

#### 4.7.1. Description
When a regression is detected, KAWACH localizes the failure to suspect source code files and synthesizes a policy-compliant unified diff patch that is validated in an isolated workspace.

#### 4.7.2. Key Capabilities & Technical Mechanics
1. **Probabilistic Culprit Localization:**
   - Evaluates failing test traces, selectors, console errors, and the commit diff.
   - Ranks candidate culprit files in `FailureCandidate` with confidence percentages ($0.0 \dots 1.0$) and technical rationales.
2. **Objective Small-Fix Safety Policies:**
   - Autonomous fix generation is constrained by strict domain rules:
     - **$\le 1$ File Touched:** Patches touching multiple files are blocked.
     - **$\le 20$ Lines Modified:** Patches exceeding 20 changed lines are classified as high-risk.
     - **Sensitive Path Blacklist:** Fixes touching `auth/`, `login/`, `payment/`, `billing/`, `migrations/`, or `.env` are strictly blocked.
     - High-risk or blocked fixes escalate automatically to human engineering review.
3. **Scratch Replay Validation:**
   - The proposed patch is applied to an isolated scratch copy of the codebase.
   - The target application is recompiled, and the failing test is re-run through the 3x verifier.
   - If the test passes 3/3 times, the fix status is certified as `validated`.
4. **Zero Direct Push Invariant:**
   - Enforced by policy (`ALLOW_DIRECT_PUSH = False`). KAWACH will **never** push fixes directly to a main or release branch. Validated fixes are opened exclusively as Pull Requests.
5. **Rich GitHub PR Reporting:**
   - Formats a comprehensive Markdown PR comment containing:
     - Test run summary (passed, failed, regression count).
     - Verified defect details with 3x verification badges.
     - Ranked suspect files with confidence ratings.
     - Suggested unified diff patch with validation certification.

---

### Feature 4.8: Production LLM Layer & Sliding-Window Rate Limiting

#### 4.8.1. Description
A resilient, cost-aware LLM provider abstraction supporting Groq and OpenAI-compatible endpoints with dynamic sliding-window rate limiting, token reservation budgeting, and automatic HTTP 429 recovery.

#### 4.8.2. Key Capabilities & Technical Mechanics
1. **Calibrated Schema Token Budgeting:**
   - Groq calculates TPM consumption based on upfront reservations: $\text{requested} = \text{prompt\_tokens} + \text{max\_tokens}$.
   - Default 4096-token reservations quickly exhaust rate limits. KAWACH assigns calibrated budgets per schema:
     - `explore_summary`: 600 tokens
     - `reviewer`: 600 tokens
     - `planner`: 1,500 tokens
     - `script_writer`: 900 tokens
     - `bug_reporter`: 800 tokens
     - `self_healing`: 750 tokens
2. **Dual Sliding-Window Rate Limiter (`GroqRateLimiter`):**
   - Tracks requests and tokens across rolling 60-second deques with microsecond timestamps.
   - Enforces configurable limits (default 30 RPM, 6,000 TPM) and minimum anti-burst intervals (2.0s).
   - Dynamically clamps `max_tokens` when rolling usage approaches ceiling limits.
3. **Authoritative Header Synchronization & 429 Backoff:**
   - Synchronizes limits with response headers: `x-ratelimit-remaining-tokens`, `x-ratelimit-remaining-requests`, `x-ratelimit-reset-tokens`.
   - On HTTP 429, parses `retry-after` and error text (`Limit X, Requested Y`), dynamically scales down requested tokens, executes exponential backoff with jitter, and falls back to `llama-3.1-8b-instant` if saturation persists.
4. **Atomic Usage Accounting:**
   - Tracks prompt tokens, completion tokens, and dollar costs per run, persisting updates via atomic file operations (`os.fsync`).

---

### Feature 4.9: Multi-Tenancy, Scopes & API Token Management (Task A1)

#### 4.9.1. Description
Enterprise access control separating interactive browser sessions from programmatic CI/CD and MCP agents, backed by cryptographically hashed API tokens and scoped permissions.

#### 4.9.2. Key Capabilities & Technical Mechanics
1. **Dual Authentication Pipeline:**
   - Seamlessly accepts either:
     - Interactive session JWT cookies (issued via `/api/v1/auth/login`).
     - Header-based API tokens: `Authorization: Bearer kw_live_<token>`.
2. **SHA-256 Hashing at Rest:**
   - Plaintext tokens are returned exactly once upon creation. The database stores exclusively the `SHA-256` hash.
3. **Granular Auth Scopes:**
   - Enforces 6 discrete scopes: `runs:read`, `runs:write`, `tests:read`, `tests:write`, `fixes:apply`, `tokens:admin`.
   - Tokens provisioned with `runs:read` receive `403 Forbidden` on test creation or auto-fix execution.
4. **Session-Only Token Management:**
   - Programmatic API tokens cannot create, view, or revoke other API tokens (`require_session_auth`).
5. **Caller Audit Tracking:**
   - Every system mutation logs `client_type` ("web", "github", "mcp") in the audit trail.

---

### Feature 4.10: Next.js 16 Web Dashboard (`apps/web`)

#### 4.10.1. Description
A modern web application providing deep visibility into every phase of the QA lifecycle, real-time worker monitoring, and interactive test catalog review.

#### 4.10.2. Page Specifications & Views
1. **Start & Preflight (`/start`):**
   - Validates target application URL connectivity.
   - Uploads and previews markdown functional specifications.
   - Configures execution mode (Autonomous vs. Manual) and budgets (time, depth, workers).
2. **Catalog Review Gate (`/catalog/[runId]`):**
   - Active in Manual Mode.
   - Renders interactive data table of proposed tests with risk badges and spec links.
   - Allows inline editing, approving/rejecting individual tests, and adding ad-hoc test prompts.
3. **Real-Time Execution Cockpit (`/execution/[runId]`):**
   - Displays live screenshots of parallel workers (`w1.png`, `w2.png`).
   - Streams live pipeline logs via Server-Sent Events (SSE).
   - Tracks overall progress, active stage, and elapsed time.
4. **Bug Deep Dive & Visual Replay (`/results/[runId]`):**
   - Detailed defect inspection view.
   - Embedded video player for failure recordings and high-resolution screenshot modal.
   - Tabbed inspectors for console errors, network request waterwalls, and Playwright execution traces.
   - Visual 3x verification indicator pips (e.g., green-green-green for 3/3 confirmed).
5. **Executive KPI & Coverage Report (`/reports/[runId]`):**
   - Executive metrics: Pass/Fail rate, Wall-clock execution time, Total LLM token usage and cost.
   - Interactive 3D Coverage Matrix visualization.
   - One-click export of markdown audit report (`report.md`) and standalone Playwright project (ZIP).
6. **Project & Regression Hub (`/projects/[projectId]`):**
   - Project credential and environment configuration.
   - Saved test library manager.
   - Commit regression history with first-failing-commit highlights and auto-fix status badges.

---

### Feature 4.11: Standalone Test Suite Packager (Export Mode)

#### 4.11.1. Description
Eliminates vendor lock-in. Any completed test run can be exported as a standalone, production-ready Playwright TypeScript repository that runs entirely independent of KAWACH.

#### 4.11.2. Key Capabilities & Technical Mechanics
- Assembles an in-memory ZIP archive containing:
  - All verified passing test scripts (`*.spec.ts`).
  - Rewritten import paths pointing to local `./fixtures` helpers.
  - Complete `playwright.config.ts` pre-configured for Chromium, Firefox, and WebKit.
  - Standalone `package.json` with Playwright dependencies and test scripts.
  - `README.md` with instructions for running locally or in GitHub Actions.

---

## 5. Security & Sandbox Guardrails

KAWACH implements enterprise-grade security controls designed for running untrusted web applications and interacting with third-party codebases:

```
+-------------------------------------------------------------------------------+
|                             SECURITY GUARDRAILS                               |
+-------------------------------------------------------------------------------+
|  1. Untrusted Content Sandboxing:                                             |
|     - All page HTML, DOM text, and repo diffs are wrapped in                  |
|       <untrusted_content> tags with strict anti-prompt-injection prompts.     |
|                                                                               |
|  2. Zero Plaintext Credential Exposure:                                       |
|     - Passwords isolated to runs/<id>/secrets.json with POSIX 0600 permissions|
|     - secrets.json and input.json are blacklisted from API file endpoints.    |
|     - Passwords never appear in logs, prompts, or reports.                   |
|                                                                               |
|  3. Target Domain SSRF Whitelisting:                                          |
|     - Requests restricted to ALLOWED_HOSTS; off-domain navigation is blocked  |
|       and logged to blocked_requests.jsonl.                                   |
|                                                                               |
|  4. Path Traversal Defense:                                                   |
|     - All file routes resolve canonical paths to ensure they reside strictly  |
|       within runs/<run_id>/, blocking ../ traversal attempts.                 |
|                                                                               |
|  5. Policy-Constrained Auto-Fix Invariants:                                  |
|     - ALLOW_DIRECT_PUSH = False; fixes are PR-only.                           |
|     - Max 1 file, max 20 lines; sensitive paths (auth, payment) strictly     |
|       blocked from automated PR creation.                                     |
+-------------------------------------------------------------------------------+
```

---

## 6. Persistence & Data Model Architecture

KAWACH employs a **hybrid persistence strategy** combining an enterprise relational database with self-contained, portable flat-file run bundles:

### 6.1. Relational Database Layer (SQLAlchemy 2.0 + Alembic)
The relational schema provides indexing, cross-project analytics, and multi-tenant security across 30 tables:
- **Identity & Tokens:** `users`, `refresh_tokens`, `api_tokens` (SHA-256 hashed).
- **Projects & Config:** `projects`, `spec_items`, `project_credentials`, `project_integrations`.
- **Runs & Metrics:** `runs`, `run_stage_times`, `app_maps`, `run_metrics`, `llm_usages`.
- **Tests & Decisions:** `test_cases`, `test_case_spec_refs`, `test_scripts`, `review_decisions`, `test_results`.
- **Bugs & Verification:** `bugs`, `bug_evidences`, `bug_duplicates`, `verifications`, `verification_attempts`.
- **Saved Tests & Coverage:** `saved_tests`, `saved_test_coverages`, `run_selected_tests`.
- **Commit Regression Loop:** `commit_events`, `failure_analyses`, `failure_candidates`, `fix_suggestions`.
- **Security Audit:** `audit_logs` (tracking caller identity and `client_type`).

### 6.2. Flat-File Run Bundles (`runs/<run_id>/`)
Every test run is simultaneously stored as an autonomous, self-contained directory partition:
- **Atomic File Swaps:** Disk writes write to temporary sibling files, execute `os.fsync`, and replace the target file via atomic filesystem renames (`os.replace`).
- **Zero-DB Portability:** A run directory can be zipped, moved, or inspected with standard tools (`jq`, `cat`, VS Code) without database access.
- **Run Directory Manifest:**
  - `run.json`: Stage state machine, timings, and error status.
  - `input.json`: Sanitized configuration (target URL, spec items, mode).
  - `secrets.json`: Isolated credentials (mode 0600).
  - `app_map.json`: State-graph topology and discovered journeys.
  - `catalog.json`: Planned test cases with risk scores and coverage matrix.
  - `review_log.json`: Reviewer approval/rejection audit trail.
  - `scripts/*.spec.ts`: Synthesized Playwright test scripts.
  - `results.json`: Execution results and step-level checkpoint failures.
  - `bugs.json`: Triaged defects with reproduction steps.
  - `verification/*.json`: 3x deterministic replay logs.
  - `metrics.json`: Aggregated duration, coverage, and token metrics.
  - `report.md`: Executive audit report.
  - `evidence/`: Screenshots, videos, and network/console logs.

---

## 7. API & Integration Contracts

The backend exposes a canonical **OpenAPI 3.1.0** contract encompassing **63 paths and 73 operations**:

| Path Pattern | Operations | Primary Purpose | Scope Required |
| :--- | :--- | :--- | :--- |
| `/api/v1/health` | `GET` | System liveness and dependency status | None |
| `/api/v1/auth/*` | `POST`, `GET` | Login, register, token refresh, `/me` profile | Session Auth |
| `/api/v1/auth/tokens` | `GET`, `POST`, `DELETE` | API token provisioning, listing, revocation | Session-Only (`tokens:admin`) |
| `/api/v1/projects` | `GET`, `POST` | Project catalog management | `runs:read` / `runs:write` |
| `/api/v1/projects/{id}` | `GET`, `PUT`, `DELETE` | Project detail, credentials, settings | `runs:read` / `runs:write` |
| `/api/v1/projects/{id}/saved-tests` | `GET`, `POST`, `DELETE` | Saved test library and coverage indexing | `tests:read` / `tests:write` |
| `/api/v1/projects/{id}/commits` | `GET`, `POST` | Tracked commit events & regression runs | `runs:read` / `runs:write` |
| `/api/v1/projects/{id}/commits/{cid}/analysis` | `GET` | Failure localization report & suspect files | `runs:read` |
| `/api/v1/projects/{id}/commits/{cid}/suggest-fix` | `POST` | Synthesize unified diff patch | `fixes:apply` |
| `/api/v1/projects/{id}/commits/{cid}/auto-fix` | `POST` | Open validated fix Pull Request | `fixes:apply` |
| `/api/v1/webhooks/github` | `POST` | Ingest push webhooks (HMAC-SHA256 verified) | Public (HMAC Verified) |
| `/api/v1/runs` | `GET`, `POST` | List and initiate QA runs (Idempotency-Key) | `runs:read` / `runs:write` |
| `/api/v1/runs/{id}` | `GET`, `DELETE` | Fetch run status, abort active runs | `runs:read` / `runs:write` |
| `/api/v1/runs/{id}/stream` | `GET` | Real-time Server-Sent Events (SSE) telemetry | `runs:read` |
| `/api/v1/runs/{id}/app-map` | `GET` | State-graph topology and journeys | `runs:read` |
| `/api/v1/runs/{id}/catalog` | `GET`, `POST`, `PATCH` | Test catalog inspection and review edits | `runs:read` / `runs:write` |
| `/api/v1/runs/{id}/execute` | `POST` | Resume execution from manual review gate | `runs:write` |
| `/api/v1/runs/{id}/results` | `GET` | Detailed test execution outcomes | `runs:read` |
| `/api/v1/runs/{id}/bugs` | `GET` | Triaged bugs, 3x verification status | `runs:read` |
| `/api/v1/runs/{id}/report` | `GET` | Executive markdown report | `runs:read` |
| `/api/v1/runs/{id}/export` | `GET` | Download standalone Playwright ZIP | `runs:read` |

---

## 8. Non-Functional Requirements & Performance Targets

| Dimension | Target Metric | Architectural Enforcement Mechanism |
| :--- | :--- | :--- |
| **Defect Precision** | **100% (Zero False Positives)** | Mandatory 3x clean replay verification against `/__reset`. No LLM bug judgement. |
| **Spec Requirement Recall** | **100% Traceability** | 3D Coverage Matrix validation before catalog approval. |
| **Regression Turnaround** | **< 60 seconds** | Diff-aware test selection runs only affected tests rather than full suites. |
| **Flake Resistance** | **< 0.1% Flaky Runs** | Isolated browser sandboxes, context/cookie resets, and strict non-assertion flake retry gating. |
| **Rate Limit Reliability** | **Zero HTTP 429 Crashes** | Calibrated schema budgets, sliding-window pacing, dynamic clamping, and fallback models. |
| **API Idempotency** | **100% Replay Safety** | Thread-safe `Idempotency-Key` payload hashing and GitHub webhook delivery ID tracking. |
| **Credential Security** | **Zero Plaintext Leakage** | POSIX 0600 secrets isolation, SHA-256 token hashing, and route blacklisting. |
| **Architecture Boundary** | **100% Clean Layering** | 5 enforced import-linter contracts: agents never import API or services; workflows never import API. |

---

## 9. Verification & Acceptance Baselines

The current implementation of the features described in this document satisfies the following baseline tests:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.1, pytest-8.3.4, pluggy-1.5.0
rootdir: c:\projects\aiqa
collected 112 items

apps/api/tests/test_a1_hardening.py ......                                [  5%]
apps/api/tests/test_commit_loop.py .....                                  [  9%]
apps/api/tests/test_executor_exploratory.py ......                        [ 15%]
apps/api/tests/test_explorer_deep.py ...                                  [ 17%]
apps/api/tests/test_groq_rate_limiting.py ...........                     [ 27%]
apps/api/tests/test_isolation.py .......                                  [ 33%]
apps/api/tests/test_planner_multi_level.py ....                           [ 37%]
apps/api/tests/test_saved_test_replay.py .                                [ 38%]
apps/api/tests/test_scaffolding.py ...................................    [ 70%]
apps/api/tests/test_tokens.py .......                                     [ 76%]
backend/tests/test_api.py ................                                [ 90%]
backend/tests/test_e2e_stub.py s.                                         [ 92%]
backend/tests/test_llm.py .........                                       [100%]

======================== 111 passed, 1 skipped in 73.80s ========================
```

- **Layered Architecture Boundary:**
  `lint-imports` $\to$ **5 contracts kept, 0 broken**.
- **Next.js Web Frontend:**
  `npm run build` $\to$ **Turbopack clean build**, 13 static pages generated, 0 TypeScript errors.
- **Contract Synchronization:**
  Canonical OpenAPI 3.1.0 schema generated directly from live FastAPI backend (`packages/contracts/openapi.json`), with synchronized TypeScript definitions (`apps/web/src/generated/api-types.ts`).
