# QA Reliability & Engineering Decisions Log (KAWACH)

This document records all architectural decisions, assumptions, and trade-offs made during the overhaul of the QA test-execution, verification, and evidence pipeline.

---

## 1. Concurrency and Worker Process Model
- **Decision**: In-process coordination uses thread-safe primitives (`threading.Lock` / `threading.RLock`) for in-memory states. Playwright runner sessions execute via `subprocess.run` inside `apps/runner/` with isolated workers (`--workers=N`).
- **Assumption**: Each test must execute in a completely pristine browser context (empty cookies, empty `localStorage`, empty `sessionStorage`, empty IndexedDB, fresh cache).

---

## 2. Evidence Architecture & Video Post-Processing (S2)
- **Decision**: All Playwright scripts will run with `video: { mode: 'on', size: { width: 1280, height: 720 } }`, `trace: 'on'`, `screenshot: 'on'`.
- **Post-Processing**: Because Chromium generates streaming WebM files without duration metadata in EBML headers, every completed video file will be remuxed/re-encoded via `ffmpeg` (shipping with Playwright or available on PATH) to guarantee valid duration metadata and smooth browser seeking.
- **Evidence Paths**: Evidence will be stored in deterministic, collision-free paths:
  - Run level: `runs/<run_id>/evidence/<test_id>/video.webm`, `screenshot.png`, `trace.zip`, `console.json`, `network.json`.
  - Replay level: `runs/<run_id>/verification/<bug_id>/trial_<N>/...`.

---

## 3. Verdict Engine & Status Taxonomy (S3)
- **Taxonomy**:
  - `passed`: Runner exit 0, at least 1 real assertion executed, zero unexpected errors.
  - `passed_with_issues`: Assertions passed, but first-party unexpected errors detected (console errors, unhandled exceptions, 5xx responses). Surfaced as findings.
  - `failed`: Assertion failure on application behavior.
  - `script_error`: Test broken due to invalid locator, syntax error, strict-mode violation, or data error.
  - `setup_error`: Precondition or authentication failure.
  - `environment_error`: Target connection reset, network unreachable, browser crash.
  - `flaky`: Non-deterministic result across replay attempts.
  - `inconclusive`: Zero assertions executed or missing evidence.

---

## 4. Oracle Helpers (`qa_helpers`) & Second-Opinion Arbiter
- **Decision**: Provide robust, vetted assertion helpers (`expectErrorFeedback`, `expectNoErrorFeedback`, `expectSuccessFeedback`, `uniqueData`) injected into test fixtures.
- **Arbiter**: If a test fails with "expected feedback not found", a second-opinion inspection checks the DOM text, ARIA tree, HTML5 validity, open shadow DOM, and iframes before labeling as a bug candidate.

---

## 5. Cross-Target Isolation & Stale Data Elimination (S1)
- **Decision**:
  - Eliminate the silent fallback to `examples/target-app/spec.md`. If no spec is provided, the run must either be strictly exploratory based on the explored app map or require a spec.
  - Project isolation: Every run must be strictly bound to its own project matching the target URL. Never arbitrarily assign to `user_projects[0]`.
  - Keying: Fingerprint all caches and saved tests by `(user_id, project_id, target_origin, spec_hash)`.
  - Provide `scripts/purge_stale_data.py` for audit and cleanup.
