# Deployed Sites QA Reliability & Engineering Decisions Log (KAWACH)

This document records all architectural decisions, assumptions, and trade-offs made during the overhaul of the deployed / external website testing pipeline.

---

## 1. Ethical, Legal, and Target Safety Boundaries
- **Decision**: KAWACH is strictly an engineering tool for sites the user owns or has authorization to test.
- **Rules**:
  - NO stealth plugins, bot-detection evasion, fingerprint spoofing, CAPTCHA solving, or IP rotation.
  - Standard, honest client identity: Use a normal modern desktop Chrome User-Agent string, standard Accept headers, and polite request rates.
  - Transparent Identification: Support an optional custom header `X-QA-Token: <token>` and `X-QA-Agent: Kawach-Tester/1.0` so site owners can easily allow-list automated test traffic in their WAF / Cloudflare rules.
  - Block Handling: If a site's WAF or CDN blocks automation (e.g. Cloudflare challenge, 403 Access Denied), DETECT and REPORT it honestly as an environment finding with site owner instructions; never attempt to evade the challenge or fail individual functional tests.

---

## 2. Target Fetch & Request Layer Policy (Phase 2)
- **Decision**: Establish a single, shared target fetch policy across all backend components (preflight, SSRF validation, crawler, and test runner).
- **Specifications**:
  - Standard User-Agent: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36`
  - Standard Accept Headers: `Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8`, `Accept-Language: en-US,en;q=0.9`, `Accept-Encoding: gzip, deflate, br`.
  - Redirect Handling: Follow redirects up to 10 hops; validate each hop against SSRF rules; re-resolve DNS on each connection to prevent DNS rebinding.
  - Preflight Probe: Use a lightweight GET (or GET with Range `bytes=0-4096`) instead of HEAD, because many real-world CDNs/WAFs reject HEAD requests with 403 or 405.
  - Retries & Backoff: Retry up to 2 times with exponential backoff and jitter strictly on transient network failures and 502/503/504 errors. Respect `Retry-After`. Never retry 4xx client errors.

---

## 3. Concurrency, Politeness & Rate Limiting
- **Decision**:
  - Default parallel workers for deployed targets: 2 workers (configurable), with at most 2 requests per second per worker.
  - Localhost / internal targets may use up to 4 parallel workers.
  - Warm-up: Perform a single sequential "gate" navigation before launching parallel workers to populate browser cache and avoid simultaneous burst triggers.
  - Sandbox isolation: Each test runs in a fresh `BrowserContext` with cleared cookies, localStorage, sessionStorage, and cache. Never leak state across runs.

---

## 4. Navigation & Readiness Architecture
- **Decision**: Eliminate reliance on `'networkidle'` as a page readiness signal. Real-world sites with analytics, web sockets, streaming media, or long-polling never reach networkidle and cause false timeouts.
- **Readiness Standard**:
  `DOMContentLoaded` + visible main content (body text length > 0 or landmark elements) + 500ms visual stability (no layout shifts) + 15s maximum timeout cap. If network activity continues after 15s, proceed with a recorded `slow_load` note rather than aborting.
- **Deterministic Overlay Dismissal**:
  Automatically detect and dismiss common cookie/consent dialogs and modal popups (synonyms across English, Spanish, French, German: "accept", "agree", "allow", "got it", "close", "aceptar", "entendido") before running test actions, and log the dismissal.

---

## 5. Circuit Breaker & Status Taxonomy
- **Decision**: If the target site cannot be reached or blocks automation, the test suite must NOT generate or execute dozens of doomed tests.
- **Circuit Breaker Behavior**:
  - Pre-suite Gate Navigation: If the initial gate navigation fails with an environment-class error (`blocked_by_waf`, `bad_gateway_from_target`, `dns_error`, `tls_error`, `timeout`, `empty_page`), halt immediately.
  - Suite Abort: If 3 consecutive tests fail with environment errors on initial navigation, abort the remaining tests as `not_run`.
  - New Status: `done_with_environment_issue`. Surface exactly ONE run-level environment finding with complete diagnostic evidence and owner guidance. Do not report 0/8 or 1/8 pass/fail scores.
- **Honest Error Origin**:
  Every error must be attributed to its true origin: `target`, `network`, `waf`, or `platform_proxy`. Never disguise platform errors as target failures.

---

## 6. UI Interaction & Theme Toggle Oracles (Phase 3)
- **Decision**: Replace brittle text locators with robust, multi-strategy helpers:
  - `findControl(page, intents[])`: Searches accessible role + name, aria-label, title, test-id, icon SVG classes (sun, moon, dark, light, theme, toggle, menu), and visible text; pierces open shadow DOM; returns candidate list.
  - `expectThemeToggle(page, options)`: Inspects multi-dimensional theme state before and after clicking: `<html>`/`<body>` class lists, `data-theme`/`data-mode` attributes, computed background/text luminance, CSS custom variables, and storage keys.
- **Safe Mode**:
  For all non-localhost / deployed targets, tests default to read-only safe mode. No destructive actions, no purchases, no real form submissions that trigger backend mutations.

---

## 7. In-DOM Visual Evidence & Mouse Virtualization (Phase 5)
- **Decision**: In headless Playwright Chromium, the native OS mouse pointer is invisible. To provide unambiguous video evidence of test interaction:
  - Inject a lightweight virtual cursor (`20px` circular red dot) and expanding click ripple directly into the DOM via `context.addInitScript`.
  - Virtual elements are styled with `pointer-events: none` and `z-index: 2147483647` so they never intercept clicks or distort layouts.
  - Post-process video streams with ffmpeg container remuxing, guaranteeing smooth evidentiary playback and video duration >= 3 seconds.

---

## 8. Zero-Dependency Native Node Simulator (Phase 6)
- **Decision**: Provide a deterministic testbed for external target failure modes without external internet variance or third-party test dependencies.
- **Implementation**:
  - Implemented `qa_benchmark/deployed_sim/server.js` using only Node.js standard libraries (`http`, `url`).
  - Exercises edge cases: `waf_blocked` (403 challenge vs standard desktop Chrome UA), `head_405` (Range GET fallback), `flaky_502` (transient retry), `consent_banner` (blocking overlay), `theme_variants` (icon-only toggles), and `spa_routing` (client-side hash/history transitions).

---

## 9. Browser Evaluation Bundler Isolation
- **Decision**: In modern build environments running `tsx` or `esbuild`, passing named arrow functions directly to `page.evaluate(() => { ... })` causes the transpiler to inject `__name(fn, "name")`. Because `__name` is undefined in the browser's DOM window, Playwright throws `ReferenceError: __name is not defined`.
- **Solution**:
  - All DOM evaluations in `qa_helpers.ts` are written as evaluated self-executing string literals: `page.evaluate('(() => { ... })()')`.
  - Completely eliminates bundler code injection into browser execution contexts.

---

## 10. Strict Type Soundness in QA Helpers
- **Decision**: All helper functions in `apps/runner/qa_helpers.ts` must maintain strict TypeScript typing without relying on untyped `unknown` returns from `page.evaluate`.
- **Implementation**:
  - Declared `interface ThemeState` capturing classes, attributes, computed background luminance, text luminance, and localStorage keys.
  - Return values of `getThemeState` and `findControl` are strongly typed, passing `tsc --noEmit` with zero errors.
