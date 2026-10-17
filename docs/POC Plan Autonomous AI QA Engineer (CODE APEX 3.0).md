# POC Plan: Autonomous AI QA Engineer (CODE APEX 3.0)

Oct 17, 2026 · @ojas sangwai

## Overview

The goal is one thin pipeline that works end to end for the 9 am demo, not many half-built agents.

This plan assumes 4 people, about 9 hours (23:40 to 08:30), and a demo that runs on localhost. With 3 people, merge Track A into Track C. With 2, pair B with C and A with D.

Nothing is built yet. The plan cuts PRD v1.0 down to a proof of concept: a basic frontend, a basic backend, a basic agent structure, and the glue between them. Docker is added only if time allows. If you fall behind, cut in the order given under Cut order and risks.

## Scope

The demo shows a full run: you enter a URL, prompt, spec and credentials, and the system explores the app and proposes tests. A human (or a reviewer agent) approves them, Playwright runs them, and failures become bug reports with evidence and a `.ts` script. A verifier replays each bug 3 times, and you get a report with metrics.

| Priority | Feature (PRD reference) |
| --- | --- |
| Must | Input form (FR-1) |
| Must | Explorer: bounded crawler plus LLM summary (FR-2) |
| Must | Planner: test catalog with spec links (FR-3) |
| Must | Manual catalog review: approve, remove, edit, add by prompt (FR-4) |
| Must | Script writer: one Playwright script per test (new, not in the PRD) |
| Must | Runner with evidence: screenshot, video, trace, console, network (FR-8) |
| Must | Repro report plus runnable `.ts` script (FR-9) |
| Must | Verifier: 3 replays, statuses confirmed, flaky, not reproduced (FR-10) |
| Must | Markdown report with metrics (FR-11) |
| Must | Basic UI and API tying it all together |
| Should | Autonomous Reviewer with logged reasons (FR-5) |
| Should | Rule-based exploratory probes (FR-7, simplified) |
| Should | Export passing tests (FR-12) |
| Should | Parallel workers with measured speedup (FR-6) |
| Should | Network allowlist, staging-only check, budgets (NFR-3, NFR-4, NFR-6) |
| Should | Docker compose |
| Could | Prompt-injection test page (P4-6) |
| Could | Responsive sweep (P6-2) |
| Could | "Not a bug" memory (P6-4) |
| Could | Deduplication (FR-14) |
| Could | axe accessibility checks |
| Could | HTML report |
| Out | Postgres, user accounts, full dashboard, VM sandbox, cross-browser, visual regression, CAPTCHA and 2FA, LLM-driven free exploration |

### What is real and what is simplified

Say this honestly in the pitch.

- **Explorer:** a crawler with a budget plus one LLM summary. It is not a free-roaming agent.
- **Test scripts:** the LLM writes one Playwright script per test. Playwright runs it, with no LLM at run time.
- **Exploratory Tester:** rule-based edge-case probes, with no LLM.
- **Verifier:** no LLM, as in the PRD.
- **Sandbox:** Playwright route blocking, plus Docker if time allows.

## Decisions

Settle these in the first 10 minutes, with no debate. They answer PRD open questions 1, 3 and 4. Swap the stack if you must, but decide now.

| Area | Decision |
| --- | --- |
| Orchestrator | Python, FastAPI, LangGraph |
| Browser code | All in one TypeScript Playwright project (`runner/`). Python calls it through a subprocess. This gives one Playwright install, one browser set and one Docker image. |
| Frontend | React + Vite, polling every 2 seconds. No websockets. |
| Storage | Files on disk, `runs/<run_id>/`. No database. |
| LLM | One provider behind a single `llm.py`. Use whichever you have a key and quota for. |
| Sandbox | Run on the host first. Docker is a Should. |
| Process | Skip the LOG.md ritual tonight. Use one shared checklist, one branch per track, and merge to main every hour. |

## Architecture

The React UI calls FastAPI, which runs two LangGraph graphs. The graphs call the Playwright project in `runner/` through a subprocess, and everything is saved as files under `runs/<run_id>/`.

&#91;embedded content: architecture · UI, API, two graphs, runner, target app\]

Graph 1 ends at Review. Graph 2 starts only after the QA engineer or the Reviewer agent approves the catalog.

Two graphs are simpler than one graph with interrupts, and good enough for a demo.

### API (minimum)

| Endpoint | Purpose |
| --- | --- |
| `POST /runs` | Start a run (url, prompt, spec, credentials, mode) |
| `GET /runs/{id}` | Stage, catalog, results, bugs, metrics |
| `PUT /runs/{id}/catalog` | Save the reviewed catalog |
| `POST /runs/{id}/tests` | Add a test by prompt |
| `POST /runs/{id}/execute` | Approve and run |
| `GET /runs/{id}/report` | Markdown report |
| `GET /runs/{id}/files/...` | Screenshots, videos, scripts |
| `GET /runs/{id}/export` | Zip of passing tests |

### Run stages

created, exploring, planning, awaiting\_review, scripting, running, verifying, reporting, then done or failed.

### Contracts

Use the PRD section 8 fields. Add `script` to TestCase, and add `source: exploratory` and a `grep` title to BugCandidate. The verifier replays with `npx playwright test <file> -g "<title>" --retries=0`, so planned tests and probes share one verification path.

## Timeline

The plan runs from 23:40 on 17 Oct to the 9 am presentation, with the first full run due by 03:30 and a feature freeze at 05:15.

&#91;embedded content: timeline · 6 phases, 2 milestones, to scale\]

Phases 0 to 3 build the product. After 05:15 only fixes, the benchmark and demo prep happen.

## Phase 0: Foundations

Everyone works together for 40 minutes (23:40 to 00:20) so the four tracks can then build in parallel.

- **0.1 Repo (10 min).** Create `docs/`, `contracts/`, `target-app/`, `backend/`, `runner/`, `frontend/` and `runs/` (git-ignored). Put the PRD in `docs/`.
- **0.2 Contracts (20 min, owners of Tracks B and C).** Write example JSON for AppMap, TestCase, BugCandidate, VerifierResult and Run, plus the API list from the Architecture section. The frontend builds against these as mocks, so nobody waits for the backend.
- **0.3 Demo script (5 min).** Agree on the 8 demo beats listed under Demo script. Everyone builds toward them.
- **0.4 Environment.** Share `.env.example` with the LLM key. Install Node and Python, and run `npx playwright install chromium`, on every laptop.

**Exit:** contracts committed, everyone can run Playwright, tracks assigned.

## Phase 1: Parallel build

Four tracks build at the same time against the contracts, from 00:20 to 02:30. Each track must work on its own by the end.

### Track A: Target app and ground truth

About 60 to 75 minutes, then Docker and the benchmark.

- **A1.** Build a tiny local web app with a coding agent: `/signup`, `/login`, `/dashboard` (add and delete items), `/settings` and `/logout`. Keep data in memory. Add `/__reset` to wipe state between runs.
- **A2.** Plant 8 to 10 bugs and write the spec sheet (`spec.md`) with the correct behavior for each. Suggested bugs:
  - Signup accepts an invalid email.
  - Signup accepts a password shorter than the spec minimum.
  - Wrong password shows no error.
  - Login fails for emails with capital letters.
  - Dashboard accepts an empty item title.
  - Delete removes the wrong item.
  - Back button after logout still shows the dashboard.
  - `/settings` throws a console error.
  - One intermittent failure (every second save fails) to demo the "flaky" status.
- **A3.** Write `ground_truth.json` (id, description, spec ref) and seed one test user.

### Track B: Agents and graphs

- **B1. `llm.py`.** JSON-mode output, retries, a disk cache keyed by prompt hash, and token and cost counters. The cache protects the live demo from rate limits and slow responses.
- **B2. Explorer.** `runner/explore.ts` logs in, then does a breadth-first crawl of same-origin pages. Limits are 10 pages and 90 seconds. Per page it records URL, title, headings, links, forms and fields (role, label, type), buttons, console errors and HTTP status. One LLM call turns this into an app map and context summary.
- **B3. Planner.** Input is the app map, prompt and spec. Output is 8 to 12 tests as JSON, each with id, title, description, specRef, priority and concrete steps with expected results. Rule in the prompt: one test per spec item.
- **B4. Script writer.** For each test, the LLM writes a Playwright `.spec.ts`. Rules in the prompt: role and text locators, unique data using `Date.now()` so parallel runs don't collide, assertions only from the spec's expected results, and no off-domain URLs. After writing, run `npx playwright test --list` to catch syntax and import errors. Retry once with the error fed back.
- **B5. LangGraph.** Build both graphs with stub nodes first, then fill them in. `graph.get_graph().draw_mermaid()` gives you the architecture diagram for the deck.

### Track C: Runner, verifier, API

- **C1. Playwright project.** Config sets trace, video and screenshot to retain on failure, a JSON reporter, and a configurable worker count. `fixtures.ts` records console errors and failed or 4xx/5xx requests as attachments. It also routes all off-domain requests to abort and logs them, which is the allowlist.
- **C2. Runner wrapper (Python).** Runs the specs and parses the JSON report. An `expect()` mismatch becomes a bug candidate. Locator timeouts or script crashes go into a separate "test error" bucket, not the bug list. This is the cheapest precision guard.
- **C3. Verifier.** For each candidate, replay 3 times with `--retries=0 --workers=1` and compare error messages. 3/3 is confirmed, 1/3 or 2/3 is flaky, 0/3 is not reproduced. No LLM.
- **C4. FastAPI.** Endpoints from the Architecture section. Each run is a folder plus `run.json`. Pipelines run as background tasks that update `stage` as they go.
- **C5. Report generator.** Markdown from `run.json`: summary, bug table with statuses, coverage (pages and forms exercised), tests passed, failed and errored, wall-clock time, tokens and cost.

### Track D: Frontend

- **D1.** Vite + React, `api.ts`, and mock data from the contracts.
- **D2.** New-run form: URL, prompt, spec, credentials and a mode toggle.
- **D3.** Run page with a stage stepper and polling.
- **D4.** Catalog table: edit, remove, an add-by-prompt box, and an "Approve and run" button.
- **D5.** Bug cards: severity, expected vs. actual, status badge with replay count (for example "2/3 flaky"), screenshot, a `<video>` tag as the replay viewer, script viewer, and trace download.
- **D6.** Report tab and metrics cards. Render everything as text, and use `react-markdown` without raw HTML. That covers NFR-7. Add a simple list of past runs.

**Exit:** each track works alone. The runner runs a hand-written spec against the target app. The explorer prints an app map. The UI renders mock data.

## Phase 2: Stitching

From 02:30 to 04:00 the four tracks are joined, and the first full run must work by 03:30, even if it is ugly.

- **2.1** The frontend swaps mocks for the real API.
- **2.2** Wire graph 1 to the API and run it on the target app. Check that the catalog is sensible.
- **2.3** Wire graph 2: scripts, run, triage, verify, report.
- **2.4** Do the first full end-to-end run by 03:30. List what broke and fix it in order of demo impact.
- **2.5** Tune prompts until these hold:
  - Most generated scripts run without script errors.
  - At least 5 planted bugs show up as confirmed.
  - False positives are few.

**Exit:** one click on the UI produces a report with at least one confirmed bug and one flaky bug.

## Phase 3: Should-features and safety

From 04:00 to 05:15, do these in order and stop at the freeze.

- **3.1 Autonomous Reviewer.** One LLM call returns approve or reject plus a reason for each test. It cannot add tests (DD-5). Save a `review_log` and show it in the UI.
- **3.2 Exploratory probes.** `probes.spec.ts` loops over the forms in `app_map.json` and tries empty submit, a 300-character string, unicode and emoji, double-click submit, and refresh mid-flow. It flags console errors, 5xx responses and uncaught exceptions as `source: exploratory` bugs. No LLM.
- **3.3 Export.** Zip the passing specs with `fixtures.ts` and the config. Add the endpoint and a UI button.
- **3.4 Parallel measurement.** Run the catalog once with `--workers=1` and once with `--workers=4`, and record both times in the metrics. Call `/__reset` before each run.
- **3.5 Safety.** Refuse targets that aren't localhost or an allowlisted host. Enforce budgets on pages, tests and timeouts. Show blocked off-domain requests in the report.
- **3.6 Docker.** A runner image from the official Playwright image, and a `docker-compose.yml` for the target app, backend and frontend. Stretch: run workers with `docker run --rm`. Only do the stretch if it works on the first try.
- **3.7 One novelty item.** Pick one, from cheapest and most visible:
  - **Injection page:** add `/injection` to the target app with hidden text telling the agent to visit an outside URL. Show that the run ignores it and the allowlist logs a blocked request. About 45 minutes.
  - **Responsive sweep:** run the key specs at 3 viewports using Playwright projects. About 30 minutes.
  - **"Not a bug" button:** store the bug's signature in a JSON file and skip it in future runs. About 30 minutes.

**Feature freeze at 05:15.** No new code after this, only fixes.

## Phase 4: Benchmark and demo prep

From 05:15 to 06:30, turn the frozen build into numbers and a safe demo.

- **4.1** Tag `demo-v1`.
- **4.2 Benchmark.** Run the full pipeline 3 times on the target app. Match reported bugs to `ground_truth.json` by hand. Compute recall, precision, replay rate, time and cost. Report typical numbers, and say they come from a small app you built yourself.
- **4.3 Golden run.** Save one good run as `runs/golden`. The UI must load it with no network and no LLM calls. Record a 2 to 3 minute screen recording of the whole demo as backup.
- **4.4 Human baseline (optional).** Someone who didn't plant the bugs tests the app manually for 10 minutes with a stopwatch.
- **4.5 Deck.** Add four slides: an architecture diagram, a screenshot of a confirmed bug report, the benchmark table, and "what's built / what's next".

## Phase 5: Morning

From 06:30 to 08:30, rest first, then check and rehearse. A tired demo fails more often than a missing feature does.

- [ ] Rest before anything else.
- [ ] One command starts everything (`docker compose up` or `make demo`). Test it from a clean terminal.
- [ ] Check the LLM key, the warm cache and the laptop charger.
- [ ] Check that the demo works with wifi off, except for the LLM.
- [ ] Do one rehearsal. Assign who talks and who clicks.

## Cut order and risks

If you fall behind, cut in this order: Docker, the novelty item, exploratory probes, the autonomous Reviewer, export, parallel measurement. Never cut evidence, the verifier, the report, or the UI flow.

| Risk | Fallback |
| --- | --- |
| LLM rate limit or slowness | Disk cache, and the golden run |
| LLM writes broken scripts | `--list` check, one retry, and the "test error" bucket |
| A failing test is a script mistake, not an app bug | An `expect()` mismatch is a bug; everything else is a test error |
| Docker problems | Run on the host, and mention Docker as a next step |
| Wifi at the venue | Everything is local except the LLM, and the cache covers the demo |

## Demo script

The demo takes about 5 minutes and follows eight beats.

1. Open the UI and enter the URL, prompt, spec and credentials. Start the run.
2. Show the app map the Explorer produced.
3. Show the catalog. Edit one test, add one by prompt, and approve. Then show autonomous mode with its reasons.
4. Show tests running and the stage stepper moving.
5. Open a confirmed bug (3/3): screenshot, video, expected vs. actual, and the `.ts` script. Then open the flaky one (2/3).
6. Download the exported passing tests.
7. Show the report with recall, precision, time, cost and the parallel speedup.
8. Show the safety features: the blocked-request log, and the injection page if it was built.
