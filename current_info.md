# KAWACH — Autonomous AI QA Engineer
## Current Project Information, Architecture & Living Specification

> [!IMPORTANT]
> **LIVING SPECIFICATION MAINTENANCE NOTICE:**
> This document (`current_info.md`) is the single source of truth regarding the current state, architecture, file structure, database/storage engine, domain models, and capabilities of the Autonomous AI QA Engineer project.
> **MANDATORY RULE FOR ALL AI AGENTS AND DEVELOPERS:** Whenever any file is added, modified, renamed, or deleted, or whenever any subsystem (models, agents, endpoints, graphs, UI views, tests, database/persistence) changes, you **MUST update this file immediately** to reflect the exact current state.

---

## 1. Project Description

**KAWACH** (Autonomous AI QA Engineer) is a production-grade, end-to-end automated testing system built for modern web applications. Given only a target application URL and a functional specification (`spec.md`), KAWACH autonomously discovers application topology, plans specification-linked test suites, allows human or autonomous review, generates and self-heals Playwright TypeScript test code, executes tests across sandboxed parallel browser workers, deterministically proves bugs via 3x clean replays (eliminating LLM hallucination and flakiness), and compiles executive audit-ready QA reports.

---

## 2. Aim, Objectives & Key Differentiators

### 2.1. Primary Aim
To automate the entire QA engineering lifecycle from specification analysis to verified bug reporting, reducing regression testing cycles from days to minutes while guaranteeing zero false alarms through mathematical 3x replay verification.

### 2.2. Key Differentiators
1. **Dual-Graph Agentic Engine:** Built on **FastAPI + LangGraph**, cleanly separating discovery & planning (Graph 1) from test generation, execution & defect proving (Graph 2).
2. **100% Deterministic 3x Replay Verification:** Discovered failures are triaged into assertion failures versus test errors. Assertion failures undergo 3 independent replay runs in isolated browser sandboxes (`/__reset`). Defects reproduced 3/3 are certified **Confirmed**, 1-2/3 are flagged **Flaky**, and 0/3 are marked **Not Reproduced**. No LLM is permitted to "judge" or hallucinate a bug.
3. **Self-Healing Script Generation:** If a generated Playwright script fails due to locator timeouts, syntax errors, or minor DOM drift, an automatic self-healing repair loop passes the execution trace and DOM snapshot back to the script writer agent for a 1-time automatic fix before re-testing.
4. **Strict Security Sandboxing:**
   - Web application content (HTML, page text, console errors) is treated as **untrusted data**, wrapped in `<untrusted_content>` tags with strict anti-prompt-injection guards.
   - Passwords and credentials never appear in plain text in logs, reports, exports, or LLM prompts.
   - Target domains are strictly validated against `ALLOWED_HOSTS` to prevent unauthorized web scraping or SSRF attacks.
5. **Bidirectional Spec Traceability:** Every test case maps directly to functional specification requirements (`S1...Sn`), ensuring 100% requirement coverage visibility.
6. **Zero-Lock Stub Engine (`STUB_MODE=1`):** Complete simulation engine allowing full frontend, API, and platform testing without incurring LLM costs or requiring external API keys.

---

## 3. Operational Modes & Use Cases

| Mode | Trigger | Review Gate | Execution Flow | Output |
| :--- | :--- | :--- | :--- | :--- |
| **Manual Mode** | User selects `mode="manual"` in UI or POST `/runs` | Pauses at `awaiting_review`. Human inspects catalog table, edits/approves/rejects tests, or adds ad-hoc tests via prompt modal. | Resumes upon `POST /runs/{id}/execute` | Full execution, 3x replays, and `report.md` |
| **Autonomous Mode** | User selects `mode="autonomous"` | Autonomous Reviewer agent evaluates proposed tests against spec and logs explicit approval reasons in `review_log.json`. | Automatic seamless transition from Graph 1 to Graph 2 | Hands-free CI/CD regression suite & report |
| **Export Mode** | `GET /runs/{id}/export` | N/A | Assembles in-memory zip of passing tests with rewritten import paths (`./fixtures`), `playwright.config.ts`, `package.json`, and `README.md`. | Portable, standalone Playwright test project |
| **Benchmark Mode** | Benchmark scripts | Compares discovered bugs against `ground_truth.json`. | Evaluates recall, precision, and replay stability against planted defects. | Benchmark score card (`benchmark.json`) |

---

## 4. End-to-End System Architecture

```
+----------------------------------------------------------------------------------------------------+
|                                    NEXT.JS 16 FRONTEND (Turbopack)                                 |
|  - Start / Preflight Form (/start)            - Review Gate Table (/catalog/[runId])              |
|  - Real-time Cockpit & Logs (/execution/[id]) - Bug Deep-Dive & Videos (/results/[id])             |
|  - Executive KPI & Coverage Report (/reports/[id])                                                 |
+-------------------------------------------------+--------------------------------------------------+
                                                  | REST API & SSE Event Stream (/api/v1/*, /runs/*)
                                                  v
+----------------------------------------------------------------------------------------------------+
|                                  FASTAPI APPLICATION (backend/app/main.py)                        |
|  - Dual-mounted endpoints (root + /api/v1/*)    - Spec item parser (^S\d+:)                        |
|  - Concurrency & stage guards (409)             - Frontend adapter layer (frontend_adapter.py)     |
|  - In-memory export zip packager                - Thread-safe storage manager (storage.py)         |
+-------------------------------------------------+--------------------------------------------------+
                                                  |
                         +------------------------+------------------------+
                         |                                                 |
                         v                                                 v
+--------------------------------------------------+ +-----------------------------------------------+
|        GRAPH 1: DISCOVERY & PLANNING             | |          GRAPH 2: EXECUTION & PROVING         |
|  1. Preflight URL & Spec Ingestion               | |  1. Script Writer Agent (Playwright TS code)  |
|  2. Explorer Agent: BFS Chromium Crawler         | |  2. Runner Client: 2 Workers (w1, w2)         |
|  3. App Map Synthesis (app_map.json)             | |  3. Self-Healing Repair Loop (1-time fix)     |
|  4. Planner Agent: Catalog Generation (S1..Sn)   | |  4. Failure Triage (assertion vs error)       |
|  5. Review Gate (Human or Autonomous Reviewer)   | |  5. 3x Deterministic Verifier (B01..Bn)       |
|                                                  | |  6. Bug Reporter Agent (defects synthesis)    |
|                                                  | |  7. Report Builder (metrics.json, report.md)  |
+--------------------------------------------------+ +-----------------------------------------------+
                         |                                                 |
                         +------------------------+------------------------+
                                                  v
+----------------------------------------------------------------------------------------------------+
|                                   FILE-BASED RUN PERSISTENCE (runs/<run_id>/)                      |
|  - input.json       - run.json       - app_map.json   - catalog.json   - review_log.json           |
|  - scripts/*.ts     - live/*.png     - evidence/      - results.json   - bugs.json                 |
|  - verification/    - metrics.json   - report.md      - pipeline.log   - secrets.json              |
+----------------------------------------------------------------------------------------------------+
```

---

## 5. Database & Persistence Architecture (The "Zero-Database" Flat-File System)

### 5.1. Architectural Philosophy: Why Zero-Database?
KAWACH intentionally avoids heavyweight external databases (e.g., PostgreSQL, MongoDB, Redis, or SQLite) in favor of a **directory-partitioned, atomic, thread-safe JSON flat-file storage engine**.

**Key Benefits of this Design:**
1. **Self-Contained Run Bundles:** Each test run lives in its own directory (`runs/<run_id>/`). A run can be zipped, moved, archived, shared, or re-inspected without needing database dumps or migrations.
2. **Zero External Dependencies:** No daemons to spin up, no network sockets to configure, and zero risk of connection pool exhaustion during rapid parallel testing.
3. **Full Auditability:** Every stage artifact (`app_map.json`, `catalog.json`, `results.json`, `bugs.json`) is plain JSON formatted with indentation, inspectable with standard tools (`jq`, `cat`, `curl`, VS Code).
4. **Instant Export & Portability:** Exporting a run or downloading artifacts requires only reading files from disk rather than complex database queries and joins.

### 5.2. Directory Partitioning & Run ID Scheme
- Root storage folder: Configurable via `RUNS_DIR` in `.env` (defaults to `<repo_root>/runs/`).
- Run IDs are generated via `storage.new_run_id()` using the deterministic format:
  ```
  YYYYMMDD-HHMMSS-xxxx
  ```
  *(e.g., `20261022-220551-3fa1` where `xxxx` is a 4-character cryptographically secure hex token).*
- Every run is isolated within its dedicated directory: `runs/<run_id>/`.

### 5.3. Thread Safety & Concurrency Control
- In `backend/app/storage.py`, a single-process re-entrant lock is maintained:
  ```python
  _lock = threading.RLock()
  ```
- **Thread Safety:** The lock guards all read-modify-write operations across background agent pipeline threads (`threading.Thread` daemons) and asynchronous FastAPI HTTP request handlers.
- **Race Condition Prevention:** Operations like `storage.update_run()`, `storage.set_stage()`, `storage.fail_run()`, and `storage.save_model()` acquire `_lock` to ensure atomic state updates.

### 5.4. Atomic Write & File-Swap Semantics
To prevent partial writes or file corruption if a process crashes or is killed during disk writes:
1. Data is serialized and written to a temporary sibling file in the run directory:
   ```python
   temp_path = target_path.with_suffix(target_path.suffix + f".tmp.{secrets.token_hex(4)}")
   ```
2. The file buffer is explicitly flushed and synced to physical storage:
   ```python
   f.flush()
   os.fsync(f.fileno())
   ```
3. An atomic filesystem rename replaces the target file in a single inode/MFT operation:
   ```python
   os.replace(temp_path, target_path)
   ```
4. **Windows File-Lock Resilience (`_safe_save_model`):** On Windows, where concurrent read handles can temporarily lock file replacement, `_safe_save_model` in `main.py` provides exponential backoff retries with direct file-stream write fallbacks.

### 5.5. Security & Permission Hardening
- **Secrets Isolation:** Test credentials/passwords are extracted immediately upon `POST /runs` and saved exclusively to `runs/<run_id>/secrets.json`.
- **POSIX Mode 0600:** On supported OS platforms, `secrets.json` is set to mode `0600` (readable and writable only by the process owner).
- **Zero Secret Leakage:** `secrets.json` and `input.json` are explicitly blacklisted in `get_run_file()`; requests to `/runs/{id}/files/secrets.json` or `/runs/{id}/files/input.json` return `403 Forbidden`.
- **Path Traversal Guards:** All file-serving routes verify that resolved file paths reside strictly within `runs/<run_id>/`, blocking `../` traversal and symlink escapes with `403 Forbidden`.

### 5.6. Query & Indexing Mechanism (`storage.list_runs`)
Without a traditional SQL index, run listing is optimized for high speed:
- Scans `runs/` for subdirectories containing `run.json`.
- In a single pass, loads `run.json` for base metadata and extracts aggregate counts:
  - `tests`: Count of tests from `catalog.json`.
  - `bugs`: Total count of bugs from `bugs.json`.
  - `confirmed`: Count of bugs with `status == "confirmed"`.
  - `flaky`: Count of bugs with `status == "flaky"`.
- Returns `RunListItem[]` sorted descending by `createdAt DESC` (newest runs first).

### 5.7. Canonical Run Artifact Manifest

| File / Folder | Schema / Format | Description & Purpose |
| :--- | :--- | :--- |
| `run.json` | `Run` model (JSON) | Primary run state machine: stage, stageTimes, progress, error, golden flag. |
| `input.json` | `RunInput` model (JSON) | Initial submission: targetUrl, prompt, specRaw, parsed `SpecItem[]`, mode, budgets. **Never contains password.** |
| `secrets.json` | `{"password": str}` (JSON) | Isolated credentials file with 0600 permissions. |
| `app_map.json` | `AppMap` model (JSON) | Explored site topology: pages, forms, inputs, buttons, headings, auth status. |
| `catalog.json` | `Catalog` model (JSON) | Planned test catalog: list of `TestCase` items, spec mappings, priorities, status. |
| `review_log.json` | `ReviewLog` model (JSON) | Autonomous reviewer decision log with explicit rationales for every test. |
| `scripts/<id>.spec.ts` | Playwright TypeScript | Synthesized executable test scripts for each planned test. |
| `results.json` | `Results` model (JSON) | Execution results for each test: outcome (`passed`, `assertion_failure`, `test_error`), duration, error messages. |
| `bugs.json` | `BugsFile` model (JSON) | Triaged bug candidates with reproduction steps, expected vs. actual, signatures, and status. |
| `verification/<id>.json` | `Verification` model (JSON) | 3x clean replay logs and attempt breakdown for each bug candidate. |
| `metrics.json` | `Metrics` model (JSON) | Computed execution metrics: wall-clock, coverage %, test counts, bug categories, LLM token usage. |
| `report.md` | Plain Markdown (`str`) | Executive audit report containing 11 standardized sections and artifact links. |
| `pipeline.log` | Plain text log file | Real-time agent execution log tailed by SSE stream to frontend log viewer. |
| `live/` | Directory (`*.png`) | Streaming screenshot previews for active parallel workers (`w1.png`, `w2.png`). |
| `evidence/<test_id>/` | Directory (artifacts) | Failure evidence: `screenshot.png`, `video.webm`, `trace.zip`, `console.json`, `network.json`. |
| `blocked_requests.jsonl` | JSON Lines (`BlockedRequest`) | Security audit log of blocked off-domain HTTP requests. |

### 5.8. Target Application State & Reset Architecture
- `target-app/server.js` maintains in-memory state:
  - `users`: Default seeded with `test@example.com` / `SecretPass123`.
  - `items`: Seeded with initial user items.
  - `saveCount`: Save invocation counter used for flaky bug `GT09`.
- **Deterministic Reset Endpoint (`POST /__reset`):**
  - Reverts in-memory users, sessions, and items back to clean initial seeds.
  - Resets the `saveCount` to `0`.
  - Executed before every 3x replay attempt in `verifier.py` to guarantee clean state.

---

## 6. Comprehensive Domain Models & Pydantic Schemas Specification

All domain entities in `backend/app/models.py` inherit from Pydantic v2 `BaseModel` with `ConfigDict(extra="ignore")` and exact camelCase field naming matching `docs/CONTRACTS.md`.

### 6.1. String Unions & Core Enums

```python
Stage = Literal[
    "created", "exploring", "planning", "awaiting_review",
    "scripting", "running", "verifying", "reporting",
    "done", "failed", "cancelled"
]

Mode = Literal["manual", "autonomous"]

Outcome = Literal["passed", "assertion_failure", "test_error"]

Category = Literal[
    "validation", "auth", "data", "navigation",
    "console", "network", "ui", "other"
]

Severity = Literal["critical", "high", "medium", "low"]
```

---

### 6.2. Execution Lifecycle & Configuration Models

#### `SpecItem`
Individual functional requirement parsed from user specification input.
- `id: str` — Identifier (e.g., `"S1"`, `"S2"`).
- `text: str` — Functional requirement description.

#### `Budgets`
Resource constraints and timeout ceilings governing the run.
- `maxPages: int = 10` — Maximum pages the crawler may visit.
- `exploreSeconds: int = 90` — Maximum duration for discovery phase.
- `maxTests: int = 12` — Maximum number of tests the planner may design.
- `testTimeoutMs: int = 30000` — Playwright per-test execution timeout.

#### `RunInput`
Initial user submission parameters stored in `input.json`.
- `runId: str` — Unique run identifier (`YYYYMMDD-HHMMSS-xxxx`).
- `createdAt: str` — ISO 8601 UTC timestamp.
- `targetUrl: str` — Base URL of web application under test.
- `prompt: str = ""` — Optional user testing focus or high-level instruction.
- `specRaw: str` — Raw input specification text.
- `spec: List[SpecItem] = []` — Parsed specification requirement items.
- `username: str = ""` — Target app login username/email.
- `mode: Mode = "manual"` — Execution mode (`"manual"` or `"autonomous"`).
- `budgets: Budgets` — Budget settings.

#### `Progress`
Real-time step indicator displayed in UI during active stages.
- `step: str` — Human-readable description of current task (e.g. `"Crawling application pages"`).
- `done: int` — Count of items finished in current step.
- `total: int` — Total items to process in current step.

#### `StageTime`
Timing checkpoints for an execution stage.
- `startedAt: str` — ISO 8601 UTC start timestamp.
- `endedAt: Optional[str] = None` — ISO 8601 UTC completion timestamp.

#### `Run`
Core state machine model stored in `run.json`.
- `runId: str` — Unique run identifier.
- `createdAt: str` — Creation timestamp.
- `updatedAt: str` — Last updated timestamp.
- `stage: Stage = "created"` — Current pipeline stage.
- `mode: Mode = "manual"` — Execution mode.
- `targetUrl: str` — Target application URL.
- `error: Optional[str] = None` — Fatal pipeline error message if failed.
- `progress: Optional[Progress] = None` — Current progress sub-step.
- `stageTimes: Dict[str, StageTime]` — Map of stage names to timing records.
- `golden: bool = False` — Flag designating golden demo runs.

#### `LlmUsage`
Token consumption and financial accounting model stored in `metrics.json`.
- `calls: int = 0` — Total LLM API calls executed.
- `cacheHits: int = 0` — Prompt cache hits.
- `inputTokens: int = 0` — Total prompt input tokens.
- `outputTokens: int = 0` — Total completion output tokens.
- `costUsd: float = 0.0` — Calculated cost in USD based on model pricing.

---

### 6.3. Discovery & Topology Models (`app_map.json`)

#### `FieldInfo`
Form input element details.
- `role: str` — Semantic role (e.g. `"textbox"`, `"combobox"`).
- `label: str` — Associated label text.
- `type: str` — Input type (`"text"`, `"email"`, `"password"`, etc.).
- `name: str` — Input field name or id attribute.
- `required: bool = False` — Whether the field is mandatory.

#### `FormInfo`
Form element structure.
- `id: str` — Form element identifier.
- `action: str = ""` — Form action URL.
- `method: str = "GET"` — HTTP submission method (`"GET"`, `"POST"`).
- `submitText: Optional[str] = None` — Text of submit button.
- `fields: List[FieldInfo]` — Input fields within the form.

#### `HeadingInfo`
Page header element for page context understanding.
- `level: int` — Heading level (1 for `<h1>`, 2 for `<h2>`, etc.).
- `text: str` — Heading text content.

#### `LinkInfo` & `ButtonInfo`
Interactive navigation elements.
- `LinkInfo`: `text: str`, `href: str`.
- `ButtonInfo`: `text: str`.

#### `PageInfo`
Discovered page topology.
- `url: str` — Full URL of the page.
- `path: str` — Path portion of the URL (e.g. `"/dashboard"`).
- `title: str` — Page document title.
- `status: int` — HTTP response status code (e.g. `200`, `302`).
- `requiresAuth: bool = False` — Whether page is behind login gate.
- `headings: List[HeadingInfo]` — Header elements on page.
- `links: List[LinkInfo]` — Hyperlinks on page.
- `buttons: List[ButtonInfo]` — Action buttons on page.
- `forms: List[FormInfo]` — Forms located on page.
- `consoleErrors: List[str]` — Browser console errors caught during visit.

#### `Feature`
High-level application feature identified by Explorer LLM summarization.
- `name: str` — Feature name (e.g. `"User Authentication"`).
- `description: str` — Brief description of feature capability.
- `pages: List[str]` — Paths belonging to this feature.

#### `LoginInfo`
Authentication detection status.
- `attempted: bool = False` — Whether login crawl was attempted.
- `success: bool = False` — Whether authentication succeeded.
- `url: Optional[str] = None` — Login page URL.
- `note: Optional[str] = None` — Diagnostic notes.

#### `AppMapStats` & `AppMap`
Root application map stored in `app_map.json`.
- `baseUrl: str` — Base URL of web application.
- `generatedAt: str` — Generation timestamp.
- `login: LoginInfo` — Login detection info.
- `pages: List[PageInfo]` — Discovered pages.
- `summary: str = ""` — Natural language architectural summary.
- `features: List[Feature]` — Identified application features.
- `stats: AppMapStats` — Crawl statistics (`pagesVisited`, `durationSeconds`, `budgetHit`).
- `error: Optional[str] = None` — Discovery error message if any.

---

### 6.4. Planning & Review Models (`catalog.json`, `review_log.json`)

#### `Step`
Individual test step in a planned test case.
- `n: int` — Step sequence number (1, 2, 3...).
- `action: str` — Action to perform (e.g. `"Fill 'Email' with 'user@example.com'"`).
- `expected: Optional[str] = None` — Expected intermediate outcome.

#### `TestCase`
Planned test case entity.
- `id: str` — Test identifier (e.g. `"T01"`, `"T02"`).
- `title: str` — Descriptive title of the test.
- `description: str` — Detailed test objective.
- `specRef: List[str]` — Mapped specification IDs (e.g. `["S1", "S3"]`).
- `priority: Literal["critical", "high", "medium", "low"] = "medium"` — Test importance.
- `steps: List[Step]` — Ordered test execution steps.
- `status: Literal["proposed", "approved", "rejected", "edited", "pending"] = "proposed"` — Review gate approval state.
- `origin: Literal["planner", "human", "fallback", "llm", "heuristic"] = "planner"` — Originator of test.
- `script: Optional[str] = None` — Relative path to script (e.g. `"scripts/T01.spec.ts"`).
- `scriptStatus: Literal["pending", "ok", "error"] = "pending"` — Script synthesis state.
- `scriptError: Optional[str] = None` — Error message if script generation failed.

#### `Catalog`
Complete test suite stored in `catalog.json`.
- `runId: str` — Associated run ID.
- `generatedAt: str` — Generation timestamp.
- `tests: List[TestCase]` — Planned test cases.

#### `ReviewDecision` & `ReviewLog`
Autonomous reviewer decisions stored in `review_log.json`.
- `ReviewDecision`: `testId: str`, `decision: Literal["approve", "approved", "reject", "rejected"]`, `reason: str`.
- `ReviewLog`: `runId: str`, `reviewedAt: str`, `decisions: List[ReviewDecision]`.

---

### 6.5. Test Execution, Evidence & Triage Models (`results.json`, `bugs.json`)

#### `TestResult`
Execution outcome for a single test.
- `testId: str` — Associated test ID (`"T01"`).
- `title: str` — Test title.
- `file: str` — Script file path (`"scripts/T01.spec.ts"`).
- `source: Literal["planned", "exploratory"]` — Test source.
- `outcome: Outcome` — `"passed"`, `"assertion_failure"`, or `"test_error"`.
- `durationMs: int` — Execution duration in milliseconds.
- `errorMessage: Optional[str] = None` — Failure or error message.
- `evidenceDir: Optional[str] = None` — Path to evidence artifacts folder.

#### `Results` & `ResultsSummary`
Aggregated test suite results stored in `results.json`.
- `runId: str`, `startedAt: str`, `durationSeconds: float`, `workers: int`.
- `tests: List[TestResult]` — List of all test results.
- `summary: ResultsSummary` — Summary counters (`total`, `passed`, `assertionFailures`, `testErrors`).

#### `Evidence`
Relative paths to harvested test failure artifacts.
- `screenshot: Optional[str] = None` — Screenshot path (`"evidence/T05/screenshot.png"`).
- `video: Optional[str] = None` — Video recording path (`"evidence/T05/video.webm"`).
- `trace: Optional[str] = None` — Playwright trace path (`"evidence/T05/trace.zip"`).
- `console: Optional[str] = None` — Browser console log path (`"evidence/T05/console.json"`).
- `network: Optional[str] = None` — Network request log path (`"evidence/T05/network.json"`).

#### `BugReplay` & `Bug`
Defect record stored in `bugs.json`.
- `id: str` — Bug identifier (`"B01"`, `"B02"`).
- `testId: str` — Originating test ID (`"T05"`).
- `source: Literal["planned", "exploratory"]` — Source of test.
- `title: str` — Defect title summarizing the issue.
- `grep: str` — Playwright grep expression for isolation.
- `file: str` — Test script path.
- `category: Category` — Defect category (`"auth"`, `"validation"`, `"data"`, etc.).
- `severity: Severity` — Defect impact (`"critical"`, `"high"`, `"medium"`, `"low"`).
- `specRef: List[str]` — Violated specification requirement IDs (`["S5"]`).
- `steps: List[str]` — Ordered reproduction steps.
- `expected: str` — Expected behavior per specification.
- `actual: str` — Observed defect behavior.
- `errorMessage: str` — Raw Playwright assertion error.
- `signature: str` — Deduplication hash signature.
- `duplicates: List[str]` — IDs of duplicate tests exhibiting the same defect.
- `evidence: Evidence` — Paths to failure artifacts.
- `status: Literal["candidate", "confirmed", "flaky", "not_reproduced"]` — Verification verdict.
- `replay: Optional[BugReplay]` — Replay score (`reproduced: int`, `attempts: int`).

#### `BugsFile`
Root bugs container stored in `bugs.json`.
- `runId: str` — Run ID.
- `bugs: List[Bug]` — Discovered defect records.

---

### 6.6. Prover & Verification Models (`verification/*.json`)

#### `VerificationAttempt`
Individual replay run record.
- `attempt: int` — Attempt sequence number (1, 2, 3).
- `reproduced: bool` — Whether the defect reproduced.
- `outcome: Outcome` — Execution outcome.
- `errorMessage: Optional[str] = None` — Assertion error if reproduced.
- `durationMs: int` — Replay duration in milliseconds.

#### `Verification`
Comprehensive 3x replay verification record stored in `verification/<bugId>.json`.
- `bugId: str` — Bug identifier (`"B01"`).
- `verifiedAt: str` — ISO 8601 UTC timestamp of verification run.
- `attempts: List[VerificationAttempt]` — Breakdown of the 3 replay trials.
- `reproduced: int` — Number of attempts that reproduced the defect (0 to 3).
- `status: Literal["confirmed", "flaky", "not_reproduced"]` — Certified verdict.

#### `BlockedRequest`
Security audit record stored in `blocked_requests.jsonl`.
- `ts: str` — Timestamp.
- `testId: str` — Active test ID.
- `url: str` — Blocked off-domain destination URL.
- `method: str` — HTTP request method.
- `resourceType: str` — Resource type (`"fetch"`, `"xhr"`, `"image"`, etc.).

---

### 6.7. Metrics, Benchmarking & API Views

#### `Metrics`
Aggregated run performance and coverage metrics stored in `metrics.json`.
- `runId: str` — Run ID.
- `wallClockSeconds: float` — Total execution duration.
- `stageSeconds: Dict[str, float]` — Time spent in each stage.
- `tests: MetricsTests` — Counts (`planned`, `approved`, `passed`, `failed`, `errored`).
- `bugs: MetricsBugs` — Bug breakdown (`candidates`, `confirmed`, `flaky`, `notReproduced`).
- `coverage: MetricsCoverage` — Map/form/spec coverage (`pagesInMap`, `pagesExercised`, `formsInMap`, `formsExercised`, `specItems`, `specItemsCovered`).
- `llm: LlmUsage` — Token and cost accounting.
- `parallel: Optional[ParallelTiming]` — Multi-worker speedup metrics.
- `safety: MetricsSafety` — Count of blocked off-domain requests.

#### `Benchmark` & `BenchmarkMatch`
Benchmark score card stored in `benchmark.json`.
- `runId: str`, `groundTruthTotal: int`, `truePositives: int`, `falsePositives: int`.
- `recall: float` — True positive rate against planted ground truth defects.
- `precision: float` — Discovered accuracy rate.
- `replayRate: float` — Percentage of failures verified via replay.
- `matches: List[BenchmarkMatch]` — Mappings from discovered `bugId` to `groundTruthId`.

#### `RunView`
Composite API DTO returned by `GET /runs/{id}` and `GET /api/v1/runs/{id}`.
- `run: Run` — Core run state.
- `input: RunInput` — Run input parameters (**password stripped**).
- `appMap: Optional[AppMap] = None` — Application map.
- `catalog: Optional[Catalog] = None` — Test catalog.
- `reviewLog: Optional[ReviewLog] = None` — Review log.
- `results: Optional[Results] = None` — Test execution results.
- `bugs: List[Bug] = []` — Bug reports.
- `verifications: List[Verification] = []` — Verification records.
- `metrics: Optional[Metrics] = None` — Aggregated metrics.
- `hasReport: bool = False` — Whether `report.md` exists.

#### `RunListItem`
Compact summary returned by `GET /runs` for the runs dashboard.
- `runId: str`, `createdAt: str`, `stage: Stage`, `mode: Mode`, `targetUrl: str`.
- `counts: RunListItemCounts` — Test/bug summary counters (`tests`, `bugs`, `confirmed`, `flaky`).

---

## 7. Subsystems & Included Capabilities

### 7.1. Target Testbed Application (`target-app/`)
- Lightweight Express.js multi-page web application (`http://localhost:4000`) with authentication, dashboard items, settings, and full reset endpoint (`POST /__reset`).
- Contains **9 intentionally planted ground truth bugs** (`GT01`–`GT09`):
  - `GT01`: Client-side validation bypass on `/signup` (accepts invalid email).
  - `GT02`: Signup allows weak passwords (< 8 chars).
  - `GT03`: Login with invalid password fails silently without displaying an error alert.
  - `GT04`: Login email check is case-sensitive (`User@example.com` != `user@example.com`).
  - `GT05`: Dashboard item creation accepts empty titles.
  - `GT06`: Delete button removes the first item in the list instead of the clicked item.
  - `GT07`: Missing `Cache-Control: no-store` header allows viewing cached dashboard after logout via Back button.
  - `GT08`: Settings page crashes with an unhandled `TypeError` in browser console.
  - `GT09`: Settings save throws HTTP 500 error on even save counts (flaky defect).
- Includes self-test harness (`target-app/selftest.mjs`) and specification document (`target-app/spec.md`).

### 7.2. Intelligence & Agentic Core (`backend/app/agents/`)
- **Explorer (`explorer.py`):** Drives headless Chromium crawler (`runner/explore.ts`) using breadth-first search to map interactive elements, forms, inputs, buttons, and headings into `app_map.json`.
- **Planner (`planner.py`):** Analyzes `app_map.json` and functional specs to synthesize an exhaustive test catalog (`catalog.json`) with full `S1..Sn` spec mapping, priority assignments, and step-by-step test plans. Also supports ad-hoc single test synthesis from user prompts.
- **Reviewer (`reviewer.py`):** Evaluates test catalogs during autonomous runs, providing documented rationales for test approval or rejection in `review_log.json`.
- **Script Writer (`script_writer.py`):** Generates clean, robust Playwright TypeScript test scripts utilizing custom fixtures (`runner/fixtures.ts`). Includes code sanitizers to strip markdown code blocks, enforce locator best practices, prevent hardcoded credentials, and ensure sandbox safety.
- **Bug Reporter (`bug_reporter.py`):** Ingests test failures, execution traces, screenshots, and replay outcomes to synthesize developer-grade bug reports (`bugs.json`) with exact reproduction steps, expected vs. observed behavior, error stack traces, and evidence links.

### 7.3. Workflows & Graphs (`backend/app/graphs/`)
- **LangGraph Workflows:** Orchestrates stateful multi-agent execution with error containment (`safe_node` wrappers):
  - `explore_plan.py`: Graph 1 (exploration ➔ map synthesis ➔ planning ➔ review gate).
  - `execute.py`: Graph 2 (scripting ➔ parallel execution ➔ self-healing ➔ triage ➔ 3x verification ➔ bug reporting ➔ final report compilation).
  - `stubs.py`: Zero-LLM deterministic simulation engine using contract fixtures for testing and fallback.

### 7.4. Runner & Execution Platform (`runner/`, `backend/app/runner_client.py`)
- **Playwright Test Runner:** Parallel test execution engine dividing tests across browser workers (`w1`, `w2`).
- **Fixture System (`runner/fixtures.ts`):** Provides isolated page fixtures, automatic failure screenshots, video recordings, Playwright trace zips, console error interceptors, and network activity harvesters.
- **Self-Healing Loop:** Automatically catches locator errors or runtime exceptions, requests a repaired script from the script writer agent, and re-executes.

### 7.5. Prover & Verifier (`backend/app/verifier.py`)
- **3x Clean Replay Engine:** Isolates suspected defects and executes 3 fresh replay trials against the target app, executing `POST /__reset` before each attempt to guarantee fresh state.
- Accurately classifies outcomes into **Confirmed** (3/3), **Flaky** (1-2/3), or **Not Reproduced** (0/3).

### 7.6. Report & Metrics Compiler (`backend/app/report.py`)
- **Zero-LLM Deterministic Compiler:** Computes wall-clock execution time, stage seconds, test pass/fail rates, bug categories, map/form/spec coverage percentages, and LLM token usage.
- Produces deterministic, Markdown-formatted `report.md` with table cell escaping, bug severity sorting, and embedded artifact links.

### 7.7. FastAPI Backend & Adapter (`backend/app/main.py`, `backend/app/frontend_adapter.py`)
- Dual-mounted REST endpoints supporting both canonical routes (`/runs`, `/config`, `/health`) and Next.js proxy paths (`/api/v1/*`).
- Real-time Server-Sent Events (SSE) stream (`/runs/{id}/stream` and `/api/v1/runs/{id}/logs`) streaming live execution logs and progress pings.
- In-memory export packager streaming zip files containing passing tests with rewritten import paths (`../../../runner/fixtures` ➔ `./fixtures`).
- Security middleware blocking path traversal (`../`), symlink escapes, and direct access to `secrets.json` or `input.json`.

### 7.8. Frontend Web Application (`app/`, `components/`, `hooks/`, `lib/`)
- **Next.js 16 (Turbopack) + Tailwind CSS + TanStack React Query**.
- **Views Implemented:**
  - `/` & `/start`: Run configuration and spec upload.
  - `/catalog/[runId]`: Interactive review gate with approve/reject actions and ad-hoc test generation modal.
  - `/execution/[runId]`: Live cockpit featuring dual-worker status cards, streaming screenshots, and real-time log viewers.
  - `/results/[runId]`: Filterable bug table with 3x replay badges and drawer previews.
  - `/results/[runId]/bugs/[bugId]`: Deep dive defect viewer with video player, trace download, and console/network logs.
  - `/reports/[runId]`: Executive metrics, coverage funnels, and formatted Markdown report presentation.

---

## 8. Complete Project Directory & File Structure

```text
vithackie/
+-- app/                                    # Next.js App Router (Pages, Layouts, Routing)
|   +-- api/                                # Next.js Route Handlers / API proxies
|   +-- catalog/
|   |   +-- [runId]/
|   |   |   +-- page.tsx                    # Review Gate Page (Approve/Reject/Edit Catalog)
|   |   +-- page.tsx                        # Catalog route redirect / fallback
|   +-- execution/
|   |   +-- [runId]/
|   |   |   +-- page.tsx                    # Live Execution Cockpit (Worker Cards, Live Logs)
|   |   +-- page.tsx                        # Execution route fallback
|   +-- login/
|   |   +-- page.tsx                        # Auth / Login UI placeholder
|   +-- reports/
|   |   +-- [runId]/
|   |   |   +-- page.tsx                    # Executive QA Report View (KPIs, Funnel, Markdown)
|   |   +-- page.tsx                        # Reports list fallback
|   +-- results/
|   |   +-- [runId]/
|   |   |   +-- bugs/
|   |   |   |   +-- [bugId]/
|   |   |   |   |   +-- page.tsx            # Bug Deep-Dive (Video Player, Traces, Replay Log)
|   |   |   +-- page.tsx                    # Test Results & Verified Bugs Hub
|   |   +-- page.tsx                        # Results route fallback
|   +-- start/
|   |   +-- page.tsx                        # Pre-flight Configuration & Run Start View
|   +-- favicon.ico                         # Favicon
|   +-- globals.css                         # Tailwind CSS base and theme definitions
|   +-- layout.tsx                          # Root Application Shell layout
|   +-- page.tsx                            # Root Landing Page (redirects to /start)
+-- backend/                                # Python Agentic Backend Subsystem
|   +-- .llm_cache/                         # Local disk cache for LLM requests (deterministic)
|   +-- app/                                # FastAPI application and agent modules
|   |   +-- agents/                         # Autonomous Agent implementations
|   |   |   +-- __init__.py                 # Agents package export
|   |   |   +-- bug_reporter.py             # Bug Reporter Agent (defect synthesis)
|   |   |   +-- explorer.py                 # Explorer Agent (crawler + page summary)
|   |   |   +-- planner.py                  # Test Planner Agent (catalog generation)
|   |   |   +-- reviewer.py                 # Reviewer Agent (autonomous catalog approval)
|   |   |   +-- script_writer.py            # Script Writer Agent (Playwright TS synthesis)
|   |   +-- fake_llm/                       # Canned LLM responses for STUB_MODE / LLM_PROVIDER=fake
|   |   |   +-- _example.json               # Schema example
|   |   |   +-- bug_report.json             # Canned bug reports
|   |   |   +-- explore_summary.json        # Canned page discovery summary
|   |   |   +-- planner_catalog.json        # Canned 11-test catalog
|   |   |   +-- planner_single.json         # Canned single ad-hoc test
|   |   |   +-- script_writer.txt           # Canned Playwright test script
|   |   +-- graphs/                         # LangGraph Orchestration Workflows
|   |   |   +-- __init__.py                 # Graphs package entrypoint
|   |   |   +-- execute.py                  # Graph 2: Scripting, Running, Proving, Reporting
|   |   |   +-- explore_plan.py             # Graph 1: Pre-flight, Crawling, Planning, Review
|   |   |   +-- stubs.py                    # Deterministic stub simulation engine
|   |   +-- prompts/                        # System prompts for LLM agents
|   |   |   +-- _guard.md                   # Anti-prompt-injection security guard template
|   |   |   +-- bug_reporter.md             # Bug reporter instructions and schema
|   |   |   +-- explore_summary.md          # Explorer page summarization prompt
|   |   |   +-- planner.md                  # Test catalog planning prompt
|   |   |   +-- planner_single.md           # Single test synthesis prompt
|   |   |   +-- script_writer.md            # Playwright TS code generation prompt
|   |   +-- __init__.py                     # App package initialization
|   |   +-- config.py                       # App configuration, settings, and env vars
|   |   +-- frontend_adapter.py             # DTO mapping and proxy adapter for frontend UI
|   |   +-- llm.py                          # Multi-provider LLM client with rate limiting & caching
|   |   +-- main.py                         # FastAPI server, REST endpoints, SSE stream, exports
|   |   +-- models.py                       # Pydantic v2 domain schemas (Run, Catalog, Bug, etc.)
|   |   +-- prompts.py                      # Prompt loader and untrusted data wrapping helpers
|   |   +-- report.py                       # Zero-LLM metrics and Markdown report generator
|   |   +-- runner_client.py                # Playwright execution driver & self-healing harness
|   |   +-- storage.py                      # Thread-safe JSON file-based run storage manager
|   |   +-- verifier.py                     # Deterministic 3x clean replay verifier engine
|   +-- scripts/                            # Operational & verification scripts
|   |   +-- dump_graphs.py                  # Generates Mermaid diagram files for graphs
|   |   +-- export_schemas.py               # Exports Pydantic schemas to contracts/schemas/
|   |   +-- generate_samples.py             # Generates sample JSON files from contracts
|   |   +-- llm_smoke.py                    # Smoke test for live LLM providers
|   |   +-- validate_samples.py             # Validates contract sample JSONs against models
|   |   +-- verify_live.py                  # Live end-to-end verification script against target app
|   +-- tests/                              # Pytest test suite (55 tests)
|   |   +-- conftest.py                     # Pytest shared fixtures
|   |   +-- test_api.py                     # API endpoints, security, validation, export tests
|   |   +-- test_bug_reporter.py            # Bug reporter agent unit tests
|   |   +-- test_explorer.py                # Explorer agent unit tests
|   |   +-- test_graphs.py                  # LangGraph explore-plan & execute workflow tests
|   |   +-- test_llm.py                     # LLM client, fake provider, cache, and token tests
|   |   +-- test_planner.py                 # Planner agent unit tests
|   |   +-- test_report.py                  # Metrics calculation and report generator tests
|   |   +-- test_runner_client.py           # Playwright runner client & execution tests
|   |   +-- test_script_writer.py           # Script writer agent & code sanitizer tests
|   |   +-- test_verifier.py                # 3x replay harness and classification tests
|   +-- requirements.txt                    # Python dependencies
+-- components/                             # React UI Component Library
|   +-- features/
|   |   +-- StartTestForm.tsx               # URL, Spec, Mode, and Credentials submission form
|   +-- layout/
|   |   +-- AppShell.tsx                    # Main application wrapper with nav and footer
|   |   +-- Sidebar.tsx                     # Side navigation bar
|   |   +-- TopBar.tsx                      # Top status bar with active run switcher
|   +-- providers/
|   |   +-- QueryProvider.tsx               # TanStack React Query provider
|   +-- ui/                                 # Reusable atomic UI components
|       +-- BudgetMeter.tsx                 # Budget usage display meter
|       +-- Button.tsx                      # Styled button with variants
|       +-- Card.tsx                        # Glassmorphism container card
|       +-- Checkbox.tsx                    # Accessible form checkbox
|       +-- Chip.tsx                        # Status and severity badges
|       +-- CodeBlock.tsx                   # Syntax-highlighted code container
|       +-- ConnectionBadge.tsx             # Backend health & SSE connection indicator
|       +-- DataTable.tsx                   # Sortable, filterable table
|       +-- Dialog.tsx                      # Accessible modal dialog
|       +-- Drawer.tsx                      # Slide-out preview drawer
|       +-- DropdownMenu.tsx                # Action dropdown menu
|       +-- EmptyState.tsx                  # Empty data placeholder
|       +-- FileDropzone.tsx                # Drag-and-drop file upload for specs
|       +-- LogViewer.tsx                   # Streaming real-time log terminal viewer
|       +-- ReplayPips.tsx                  # 3x replay visualization dots (green/amber/red)
|       +-- RunSwitcher.tsx                 # Active run selector dropdown
|       +-- Skeleton.tsx                    # Loading skeleton placeholder
|       +-- Stepper.tsx                     # Pipeline progress stage indicator
|       +-- Switch.tsx                      # Toggle switch component
|       +-- Tabs.tsx                        # Multi-panel tab switcher
|       +-- Toast.tsx                       # Notification alerts
|       +-- Tooltip.tsx                     # Interactive hover tooltips
|       +-- WorkerCard.tsx                  # Sandbox worker card with live screenshots
+-- contracts/                              # Architecture Contracts & Golden Samples
|   +-- samples/                            # Golden contract sample files
|   |   +-- files/                          # Sample execution evidence and scripts
|   |   |   +-- evidence/                   # Screenshots, videos, network, and console logs
|   |   |   +-- scripts/                    # Sample Playwright TS script
|   |   |   +-- report.md                   # Sample final markdown report
|   |   +-- app_map.sample.json             # Reference explored application map
|   |   +-- bugs.sample.json                # Reference triaged and verified bug list
|   |   +-- catalog.sample.json             # Reference 11-test catalog
|   |   +-- metrics.sample.json             # Reference run metrics
|   |   +-- results.sample.json             # Reference Playwright execution results
|   |   +-- review_log.sample.json          # Reference autonomous reviewer decisions
|   |   +-- run_view.*.sample.json          # Reference API run views across all stages
|   |   +-- runs_list.sample.json           # Reference runs list
|   |   +-- verification.B01.sample.json    # Reference 3x replay verification record
|   +-- schemas/                            # 40+ exported JSON Schemas matching models
|   +-- types.ts                            # Canonical TypeScript interfaces matching models.py
+-- demo-data/                              # Golden run artifacts for demo presentations
+-- docs/                                   # Project Documentation & Architecture RFCs
|   +-- AGENT_RULES.md                      # Strict operational rules for AI agents
|   +-- agentic_implementation.md           # Implementation log for LangGraph agents
|   +-- API_CONTRACT.md                     # REST API specification for frontend
|   +-- CHECKLIST.md                        # Master project development checklist
|   +-- CONTRACTS.md                        # Core system schemas, files, and signatures
|   +-- graph1.mmd                          # Mermaid diagram for Graph 1
|   +-- graph2.mmd                          # Mermaid diagram for Graph 2
|   +-- KAWACH_FRONTEND.md                  # Frontend requirements and design tokens
|   +-- p01.md - p08.md                     # Development track prompts and specifications
|   +-- report_example.md                   # Compiled sample QA report
|   +-- work_distribution.md                # Multi-developer branch and track allocation
+-- hooks/
|   +-- useRunStream.ts                     # React hook for SSE live log streaming & polling
+-- lib/
|   +-- api/
|   |   +-- client.ts                       # Typed HTTP API client using fetch
|   |   +-- config.ts                       # API endpoints and base URL configuration
|   |   +-- hooks.ts                        # React Query hooks for queries and mutations
|   +-- mocks/
|   |   +-- devMockService.ts               # Client-side dev mock responses
|   +-- store/
|   |   +-- uiStore.ts                      # Client-side UI state management
|   +-- utils.ts                            # General utility functions
+-- runner/                                 # Playwright Test Execution Environment
|   +-- hand-written/                       # Reference hand-crafted Playwright scripts (T90..T93)
|   +-- tests-smoke/                        # Smoke tests validating Playwright execution
|   +-- explore.ts                          # Playwright BFS web crawler script
|   +-- fixtures.ts                         # Custom Playwright test fixtures (video, trace, worker)
|   +-- playwright.config.ts                # Playwright test runner configuration
|   +-- tsconfig.json                       # TypeScript config for runner
+-- target-app/                             # Vulnerable Express.js Demo Web App
|   +-- ground_truth.json                   # Ground truth definitions for planted bugs (GT01..GT09)
|   +-- selftest.mjs                        # Verification script verifying planted bugs
|   +-- server.js                           # Express application server (Port 4000)
|   +-- spec.md                             # Specification requirements (S1..S11)
+-- types/
|   +-- index.ts                            # Global frontend TypeScript types
+-- .env                                    # Active environment configuration
+-- .env.example                            # Template environment configuration
+-- .gitignore                              # Git exclusion patterns
+-- AGENTS.md                               # Framework rules and guidelines
+-- current_info.md                         # LIVING GROUND-TRUTH SPECIFICATION (this file)
+-- HANDOFF.md                              # Engineering handoff & architecture report
+-- Makefile                                # Orchestration shortcuts (setup, run, test)
+-- middleware.ts                           # Next.js API proxy and request routing
+-- next.config.ts                          # Next.js 16 compiler configuration
+-- package.json                            # Root package configuration (Next.js dependencies)
+-- README.md                               # Project quickstart guide
+-- tsconfig.json                           # TypeScript configuration for frontend
```

---

## 9. Port Allocation & Runbook

### 9.1. Ports
- **Target App:** `http://localhost:4000`
- **FastAPI Backend:** `http://localhost:8000`
- **Next.js Web UI:** `http://localhost:3000` (or `http://localhost:5173`)

### 9.2. Quickstart Execution Runbook

#### 1. Start the Demo Target Application (Terminal 1)
```bash
cd target-app
npm install
node server.js
```

#### 2. Start the FastAPI Agent Backend (Terminal 2)
```bash
# In project root with active .venv:
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000 --reload
```

#### 3. Start the Next.js Frontend Dashboard (Terminal 3)
```bash
# In project root:
npm install
npm run dev
```

#### 4. Run the Full Backend Test Suite
```bash
cd backend
..\.venv\Scripts\python.exe -m pytest -v
```
*(Currently 55 tests pass cleanly in ~35 seconds).*

---

## 10. Living Document Maintenance Protocol

To ensure this file never becomes stale:
1. **Adding a New File:** Append its path, purpose, and subsystem to Section 8.
2. **Modifying an Agent or Workflow:** Update Section 7 with the updated logic, capabilities, or parameters.
3. **Changing API Routes or Ports:** Update Section 4, 7.7, and 9.1.
4. **Updating Models or Storage:** Update Section 5 (Database & Persistence) and Section 6 (Domain Models).
5. **Adding Test Cases or Planted Bugs:** Update Section 7.1 and 7.8.
