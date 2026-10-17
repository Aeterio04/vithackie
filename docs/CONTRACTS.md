# CONTRACTS — single source of truth

If you need to change anything in this file, stop and say "CONTRACT CHANGE NEEDED: <what and why>" in your final message. Do not silently deviate.

## 0. Conventions

- All JSON keys are **camelCase**. In Python use the same names on the pydantic v2 models (no aliases).
- All paths inside JSON files are **relative to the run folder** (`runs/<runId>/`) and use forward slashes.
- Timestamps are ISO 8601 UTC strings (`2026-10-18T01:23:45Z`).
- IDs: run `YYYYMMDD-HHMMSS-xxxx` (4 hex chars); planned test `T01`, `T02`, …; probe test `X01`, `X02`, …; bug `B01`, `B02`, …; spec item `S1`, `S2`, …; ground-truth bug `GT01`, …
- Test titles always start with the test ID and a colon: `T05: Signup rejects an invalid email`. The title prefix `T05:` is the `grep` used for replay.
- Ports: target app 4000, backend 8000, frontend 5173.
- LLM output is always parsed as JSON and validated against the pydantic models before it is saved.

## 1. Repo layout and ownership

```
repo/
  docs/            PRD.md  CONTRACTS.md  AGENT_RULES.md  CHECKLIST.md
  contracts/       types.ts  schemas/*.json  samples/*.json  samples/files/**
  target-app/      Track A      (Node + Express demo app with planted bugs)
  backend/         Python package `app`
    app/config.py models.py storage.py            Phase 0 (change only by agreement)
    app/llm.py prompts.py prompts/*.md            Track B
    app/agents/*.py  app/graphs/*.py  app/fake_llm/*.json    Track B
    app/runner_client.py verifier.py report.py main.py       Track C
    scripts/         export_schemas.py validate_samples.py + later scripts
  runner/          Track C      (TypeScript Playwright project; runner/explore.ts is Track B)
  frontend/        Track D      (React + Vite)
  runs/            git-ignored  (all run output)
  demo-data/golden/   committed copy of one good run
  .env.example  Makefile  docker-compose.yml (later)
```

An agent edits only the files its prompt says it owns. Everything else is read-only for that agent.

## 2. Environment variables

Backend and tools read these from `.env` (copy `.env.example`).

```
LLM_PROVIDER=anthropic            # anthropic | openai | fake
LLM_MODEL=claude-sonnet-5-5       # any model your key can use
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
LLM_PRICE_IN_PER_MTOK=0           # USD per million input tokens, from your provider's price page
LLM_PRICE_OUT_PER_MTOK=0          # USD per million output tokens
LLM_CACHE=on                      # on | off | readonly
ALLOWED_HOSTS=localhost,127.0.0.1
MAX_PAGES=10
EXPLORE_SECONDS=90
MAX_TESTS=12
TEST_TIMEOUT_MS=30000
RUNS_DIR=runs
STUB_MODE=0                       # 1 = graphs fake each stage from contracts/samples (no LLM, no browser)
VERIFY_PARALLEL=1                 # number of bugs verified at the same time (keep 1 so flaky bugs behave)
BUGS_OFF=                         # target app only: comma list of GT ids to switch off, or "all"
```

Variables the **Python backend sets for every Playwright subprocess**:

```
BASE_URL        e.g. http://localhost:4000
SPEC_DIR        absolute path of the folder holding the .spec.ts files to run
OUTPUT_DIR      absolute path for traces, videos, screenshots (Playwright outputDir)
JSON_REPORT     absolute path of the Playwright JSON report file
WORKERS         number of workers
TEST_TIMEOUT_MS per-test timeout
ALLOWED_HOSTS   comma list, same as above
BLOCKED_LOG     absolute path of a .jsonl file for blocked off-domain requests
VISITED_DIR     absolute folder; the fixture writes <testId>.json with visited URLs
TEST_USERNAME   test account username
TEST_PASSWORD   test account password
APP_MAP_PATH    absolute path of app_map.json (probes only)
```

Playwright command shape (always run with `cwd=runner/`):

```
npx playwright test --config playwright.config.ts [<file> ...] [-g "<grep>"] --workers=<N> --retries=0
```

## 3. Run stages

`created → exploring → planning → awaiting_review → scripting → running → verifying → reporting → done` and `failed` (from any stage, with `run.error` set).

Graph 1 covers created → awaiting_review (autonomous mode continues straight into graph 2). Graph 2 covers scripting → done.

## 4. Run folder layout

```
runs/<runId>/
  run.json                 Run
  input.json               RunInput (no password)
  secrets.json             { "password": "..." }   never returned by the API, never logged, never sent to an LLM
  explore_raw.json         crawler output (AppMap without summary/features)
  app_map.json             AppMap
  catalog.json             Catalog
  review_log.json          ReviewLog          (autonomous mode only)
  llm_usage.json           LlmUsage
  scripts/T01.spec.ts ...  one file per approved test
  scripts/probes/          (optional) copied probe specs
  raw/
    playwright-main.json   raw Playwright JSON report of the main run
    playwright-probes.json raw JSON report of the probes run
    test-results/          Playwright outputDir (traces, videos, screenshots)
    visited/<testId>.json  visited URLs per test
    verify/<bugId>/<attempt>/...   replay raw output
  results.json             Results
  bugs.json                BugsFile
  verification/B01.json    Verification
  evidence/<testId>/screenshot.png video.webm trace.zip console.json network.json
  blocked_requests.jsonl   one BlockedRequest per line
  parallel.json            ParallelTiming        (Should)
  benchmark.json           Benchmark             (written by hand/scripts in Phase 4)
  metrics.json             Metrics
  report.md                the Markdown report
```

## 5. JSON shapes (TypeScript notation; Python models mirror these exactly)

```ts
type Stage = "created"|"exploring"|"planning"|"awaiting_review"|"scripting"|"running"|"verifying"|"reporting"|"done"|"failed";
type Mode = "manual"|"autonomous";

interface SpecItem { id: string; text: string }                       // id "S1"
interface Budgets { maxPages: number; exploreSeconds: number; maxTests: number; testTimeoutMs: number }

interface RunInput {
  runId: string; createdAt: string; targetUrl: string; prompt: string;
  specRaw: string; spec: SpecItem[]; username: string; mode: Mode; budgets: Budgets;
}

interface Run {
  runId: string; createdAt: string; updatedAt: string; stage: Stage; mode: Mode; targetUrl: string;
  error: string | null;
  progress: { step: string; done: number; total: number } | null;   // e.g. "Replaying B03 (2/3)"
  stageTimes: Record<string, { startedAt: string; endedAt: string | null }>;
  golden: boolean;                                                  // true only for the recorded demo run
}

interface LlmUsage { calls: number; cacheHits: number; inputTokens: number; outputTokens: number; costUsd: number }

// ---- explorer ----
interface FieldInfo { role: string; label: string; type: string; name: string; required: boolean }
interface FormInfo { id: string; action: string; method: string; submitText: string | null; fields: FieldInfo[] }  // id like "/signup#form0"
interface PageInfo {
  url: string; path: string; title: string; status: number; requiresAuth: boolean;
  headings: { level: number; text: string }[];
  links: { text: string; href: string }[];
  buttons: { text: string }[];
  forms: FormInfo[];
  consoleErrors: string[];
}
interface Feature { name: string; description: string; pages: string[] }
interface AppMap {
  baseUrl: string; generatedAt: string;
  login: { attempted: boolean; success: boolean; url: string | null; note: string | null };
  pages: PageInfo[];
  summary: string; features: Feature[];
  stats: { pagesVisited: number; durationSeconds: number; budgetHit: "pages" | "time" | null };
  error: string | null;
}

// ---- planner / reviewer ----
interface Step { n: number; action: string; expected: string | null }
interface TestCase {
  id: string; title: string; description: string; specRef: string[];
  priority: "high"|"medium"|"low"; steps: Step[];
  status: "proposed"|"approved"|"rejected";
  origin: "planner"|"human"|"fallback";
  script: string | null;                                   // "scripts/T05.spec.ts"
  scriptStatus: "pending"|"ok"|"error"; scriptError: string | null;
}
interface Catalog { runId: string; generatedAt: string; tests: TestCase[] }
interface ReviewLog { runId: string; reviewedAt: string; decisions: { testId: string; decision: "approve"|"reject"; reason: string }[] }

// ---- runner / triage ----
type Outcome = "passed"|"assertion_failure"|"test_error";
interface TestResult {
  testId: string; title: string; file: string; source: "planned"|"exploratory";
  outcome: Outcome; durationMs: number; errorMessage: string | null; evidenceDir: string | null;
}
interface Results {
  runId: string; startedAt: string; durationSeconds: number; workers: number;
  tests: TestResult[];
  summary: { total: number; passed: number; assertionFailures: number; testErrors: number };
}

type Category = "validation"|"auth"|"data"|"navigation"|"console"|"network"|"ui"|"other";
type Severity = "critical"|"high"|"medium"|"low";
interface Evidence { screenshot: string|null; video: string|null; trace: string|null; console: string|null; network: string|null }
interface Bug {
  id: string; testId: string; source: "planned"|"exploratory";
  title: string; grep: string; file: string;                // file e.g. "scripts/T05.spec.ts"
  category: Category; severity: Severity; specRef: string[];
  steps: string[]; expected: string; actual: string;
  errorMessage: string; signature: string; duplicates: string[];   // testIds merged into this bug
  evidence: Evidence;
  status: "candidate"|"confirmed"|"flaky"|"not_reproduced";
  replay: { reproduced: number; attempts: number } | null;
}
interface BugsFile { runId: string; bugs: Bug[] }
interface Verification {
  bugId: string; verifiedAt: string;
  attempts: { attempt: number; reproduced: boolean; outcome: Outcome; errorMessage: string|null; durationMs: number }[];
  reproduced: number; status: "confirmed"|"flaky"|"not_reproduced";
}
interface BlockedRequest { ts: string; testId: string; url: string; method: string; resourceType: string }
interface ParallelTiming { workers1Seconds: number; workers4Seconds: number; speedup: number }

// ---- metrics / benchmark ----
interface Metrics {
  runId: string; wallClockSeconds: number; stageSeconds: Record<string, number>;
  tests: { planned: number; approved: number; passed: number; failed: number; errored: number };
  bugs: { candidates: number; confirmed: number; flaky: number; notReproduced: number };
  coverage: { pagesInMap: number; pagesExercised: number; formsInMap: number; formsExercised: number; specItems: number; specItemsCovered: number };
  llm: LlmUsage;
  parallel: ParallelTiming | null;
  safety: { blockedRequests: number };
}
interface Benchmark {
  runId: string; groundTruthTotal: number;
  matches: { bugId: string; groundTruthId: string | null }[];   // null = false positive
  truePositives: number; falsePositives: number; recall: number; precision: number; replayRate: number;
}

// ---- API views ----
interface RunView {
  run: Run; input: RunInput; appMap: AppMap | null; catalog: Catalog | null; reviewLog: ReviewLog | null;
  results: Results | null; bugs: Bug[]; verifications: Verification[]; metrics: Metrics | null; hasReport: boolean;
}
interface RunListItem {
  runId: string; createdAt: string; stage: Stage; mode: Mode; targetUrl: string;
  counts: { tests: number; bugs: number; confirmed: number; flaky: number };
}
```

## 6. Playwright fixtures (`runner/fixtures.ts`) — the only thing generated scripts may import

```ts
import { test, expect, credentials, unique } from '../../../runner/fixtures';
```

- `test`, `expect`: Playwright's, extended with an automatic fixture that (a) records console errors, page errors and failed or 4xx/5xx requests, (b) aborts and logs every request to a non-allowlisted host, (c) writes `visited/<testId>.json`, (d) attaches `console.json` and `network.json`.
- `credentials`: `{ username: string; password: string }` read from `TEST_USERNAME` and `TEST_PASSWORD`.
- `unique(prefix: string): string` returns `${prefix}-${Date.now()}-${4 random chars}`. Use it for every email, title or name a test creates.
- Scripts import **only** from this path. The path works because specs live in `runs/<runId>/scripts/`. The exporter rewrites it to `./fixtures`.
- Generated scripts navigate with relative URLs (`page.goto('/signup')`); the config sets `baseURL` from `BASE_URL`.

## 7. Python module and function signatures (Python 3.11, type-hinted, pydantic v2)

```
app/config.py      settings: Settings          # reads env; fields mirror section 2
app/models.py      one pydantic model per interface in section 5
app/storage.py
  run_dir(run_id) -> Path
  new_run_id() -> str
  read_json(run_id, rel) -> dict | list | None        # None if file missing
  write_json(run_id, rel, data) -> None                # atomic write (temp file + rename)
  load_model(run_id, rel, Model) -> Model | None
  save_model(run_id, rel, obj) -> None
  get_run(run_id) -> Run
  update_run(run_id, **fields) -> Run
  set_stage(run_id, stage, step=None, done=0, total=0) -> Run   # also maintains stageTimes
  fail_run(run_id, message) -> Run
  read_secret_password(run_id) -> str
  list_runs() -> list[RunListItem]
app/llm.py
  class LLM:
    complete_json(*, system, prompt, schema_name, run_id=None, max_tokens=4000, temperature=0.2) -> dict
    complete_text(*, system, prompt, run_id=None, max_tokens=2000, temperature=0.2) -> str
  get_llm() -> LLM
  usage(run_id) -> LlmUsage
app/prompts.py
  load_prompt(name, **vars) -> str     # reads app/prompts/<name>.md, replaces {{var}}
  untrusted(text, label) -> str        # wraps text in <untrusted_content label="..."> tags
app/agents/explorer.py       run_explorer(run_id) -> AppMap
app/agents/planner.py        plan_catalog(run_id) -> Catalog ;  plan_single_test(run_id, user_prompt) -> TestCase
app/agents/script_writer.py  write_scripts(run_id) -> Catalog
app/agents/reviewer.py       review_catalog(run_id) -> ReviewLog
app/agents/bug_reporter.py   write_bug_reports(run_id) -> list[Bug]
app/runner_client.py
  @dataclass RawRun(exit_code, report_path, stdout, stderr, duration_s)
  @dataclass ListResult(ok, error)
  run_playwright(run_id, *, files=None, grep=None, workers=4, spec_dir=None, out_name="main", extra_env=None, timeout_s=900) -> RawRun
  list_tests(run_id, file) -> ListResult
  run_tests(run_id, workers=None, include_probes=False) -> Results       # also writes evidence and results.json
  triage(run_id) -> list[Bug]                                            # writes bugs.json (status "candidate")
  is_assertion_failure(error_message) -> bool
app/verifier.py              verify_bug(run_id, bug_id) -> Verification ;  verify_all(run_id) -> list[Verification]
app/report.py                build_metrics(run_id) -> Metrics ;  build_report(run_id) -> str   # both write their files
app/graphs/__init__.py       run_explore_plan(run_id) ;  run_execute(run_id) ;  run_pipeline(run_id)
app/main.py                  FastAPI `app`
```

`STUB_MODE=1`: each graph node skips real work, sleeps 1 to 2 seconds, and copies the matching file from `contracts/samples/` into the run folder, so the UI and API can be tested with no LLM and no browser.

## 8. HTTP API (JSON unless stated; CORS allows http://localhost:5173)

```
GET  /config                    -> { allowedHosts: string[], budgets: Budgets, defaultTargetUrl: string, stubMode: boolean }
GET  /runs                      -> RunListItem[]                          newest first
POST /runs                      body { targetUrl, prompt, spec, username, password, mode } -> 201 { runId }
                                  422 { errors: [{ field, message }] }    409 if another run is active
GET  /runs/{id}                 -> RunView                                404 if unknown
PUT  /runs/{id}/catalog         body { tests: TestCase[] } -> Catalog     409 unless stage == awaiting_review
POST /runs/{id}/tests           body { prompt } -> TestCase               adds status "proposed", origin "human"
POST /runs/{id}/execute         -> 202 { stage }                          409 unless stage == awaiting_review
                                  every test not "rejected" becomes "approved"
GET  /runs/{id}/report          -> text/markdown
GET  /runs/{id}/files/{path}    -> the file (path traversal blocked)
GET  /runs/{id}/export          -> application/zip of passing tests
```

`spec` in `POST /runs` is the raw text. The backend parses it into `SpecItem[]`. Lines look like `S3: text`. A continuation line starts with two spaces.

## 9. Triage rule (single definition)

A failed Playwright test is an **assertion failure (bug candidate)** only if, after removing ANSI colour codes, its error message matches `expect\(.*?\)\.(not\.)?to\w+` and does **not** begin with `Test timeout of`. Everything else that failed (locator or navigation timeouts, `page.goto` errors, syntax or reference errors, test timeout) is a **test error**. Probes use the same rule.

Error signature: take the first 400 characters of the cleaned message, replace runs of 4 or more digits with `N`, replace anything matching `[a-z]+-\d{13}-[a-z0-9]{4}` with `U`, collapse whitespace, lower-case, then sha1 and keep 10 hex characters.

## 10. Reference target app and spec (what the demo app should do)

The demo app lives in `target-app/`. Seed user: `qa.tester@example.com` / `Passw0rd!23`. State is in memory. `GET|POST /__reset` wipes state and re-seeds. `GET /__bugs` lists enabled bug IDs.

**spec.md** (this exact text is what you paste into the New Run form):

```
S1: Signing up with a valid email and a password of at least 8 characters creates the account and lands the user on the dashboard.
S2: Signing up with an invalid email address (for example "not-an-email") is rejected with the message "Enter a valid email address".
S3: Signing up with a password shorter than 8 characters is rejected with the message "Password must be at least 8 characters".
S4: Logging in with a correct email and password lands the user on the dashboard.
S5: Logging in with a wrong password shows the message "Invalid email or password" and the user stays on the login page.
S6: Logging in is case-insensitive for the email address (QA.Tester@Example.com works the same as qa.tester@example.com).
S7: On the dashboard, adding an item with a non-empty title shows that item in the list.
S8: On the dashboard, adding an item with an empty title is rejected with the message "Title is required" and no item is added.
S9: With several items in the list, clicking Delete on an item removes only that item.
S10: On the settings page, saving a display name shows "Settings saved" every time, and the page loads without console errors.
S11: Logging out returns the user to the login page, and pressing the browser Back button afterwards does not show the dashboard.
```

**Planted bugs** (`target-app/ground_truth.json` has the same list):

| ID | Spec | Bug | Severity |
| --- | --- | --- | --- |
| GT01 | S2 | Signup accepts an invalid email | medium |
| GT02 | S3 | Signup accepts passwords shorter than 8 (it only checks for 4) | medium |
| GT03 | S5 | Wrong password shows no error message | high |
| GT04 | S6 | Login fails when the email has capital letters | high |
| GT05 | S8 | Dashboard accepts an empty item title | medium |
| GT06 | S9 | Delete removes the first item in the list instead of the clicked one | high |
| GT07 | S11 | After logout, Back shows the cached dashboard (response is cacheable) | high |
| GT08 | S10 | The settings page logs a console error and throws an uncaught TypeError on load | low |
| GT09 | S10 | Every second settings save fails with HTTP 500 (global counter; the planned "flaky" demo bug) | medium |

Accessible markup is mandatory so role and label locators work: labelled inputs, `button` elements, headings, `role="alert"` for error messages and `role="status"` for success messages.
