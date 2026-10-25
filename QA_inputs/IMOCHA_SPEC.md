# iMocha Marketing Website: QA Specification (spec.md)

**Target:** https://www.imocha.io/  (production marketing site, built on Webflow)
**Mode:** read-only. This is a live third-party production site. Tests must NEVER submit a valid form, create accounts, log in, or trigger emails. They only observe, navigate, click UI controls, and check validation feedback.
**Written from:** the homepage content as served on 2026-10-25. Link targets and section headings below were observed. Interactive behaviour (menus, accordions, widgets) was NOT observed in a browser, so every test carries a **Confidence** value:
- **High**: structure observed directly in the page source.
- **Medium**: very likely, but interaction details need confirmation.
- **Calibrate**: behaviour unknown; the first run must observe the real behaviour and report it (see calibration rules in the run prompt).

---

## 0. GLOBAL RULES (apply to every test)

| Rule | Value |
|---|---|
| Base URL | `https://www.imocha.io` (follow redirects; final host must be `www.imocha.io`) |
| Default viewport | Desktop 1440x900. Mobile tests use 390x844 (touch). Tablet tests use 768x1024. |
| Readiness | Page is ready when DOMContentLoaded fired, the main `<h1>` is visible, and layout is stable for 500 ms. Never wait for `networkidle` (analytics keep the network busy). Cap 20 s. |
| Overlays | Cookie/consent banners, chat bubbles and popups must be dismissed or ignored before interacting; record that it happened. |
| Safe mode | Forms: only empty-submit and invalid-input validation checks. Never a valid submission. Never click the "Login" button's destination form (the `app.imocha.io` app is a separate product; only its URL/host/status is checked). |
| External links | For links to other domains (YouTube, LinkedIn, app.imocha.io, etc.) check `href`, `target`, `rel`; do NOT navigate away to third-party sites except `app.imocha.io` (one GET, status only). |
| Politeness | At most 2 parallel workers and 2 requests per second against the site. |
| Third-party noise (ignored in console/network error checks) | googletagmanager, google-analytics, doubleclick, facebook, linkedin, hotjar, clarity, hubspot, hs-scripts, cookiebot, onetrust, intercom, drift, 6sense, clearbit, zoominfo, bing, adroll, favicon requests |
| First-party errors | Uncaught page exceptions, `console.error` coming from `www.imocha.io` or `cdn.prod.website-files.com` scripts, and same-origin 4xx/5xx on documents or required assets are real findings. |
| Evidence | Every test records a screenshot at the end and a step-captioned video. |
| Info-type tests | Tests marked **Type: informational** never fail the run. Their observations become findings with severity `info`/`low` (status `passed_with_issues`). |

---

## 1. REQUIREMENTS (for the coverage matrix)

| ID | Requirement |
|---|---|
| REQ-LOAD-01 | The homepage loads successfully with correct document metadata and no first-party runtime errors. |
| REQ-NAV-01 | The primary navigation exposes Products, Use Cases, Customers, Resources, Company, a Login button and a Book a Demo button, and every link goes to the correct destination. |
| REQ-NAV-02 | The mega-menus (Products, Use Cases, Resources, Company) open, list the documented links and close properly. |
| REQ-NAV-03 | The mobile navigation (hamburger) works at phone width. |
| REQ-CTA-01 | Every "Talk to an Expert" / "Book a Demo" call to action leads to the demo scheduling page. |
| REQ-HOME-01 | Each homepage section (hero, case studies, analysts, two intelligences, use cases, partners, unified system, customers, AI agents, why iMocha, FAQ, get started) is present, populated and its media loads. |
| REQ-UC-01 | The five use cases are selectable and each has a working "Learn More" link. |
| REQ-FAQ-01 | The FAQ is an accessible accordion: questions expand and collapse and show their answers. |
| REQ-WIDGET-01 | The floating "Get in touch" widget offers Schedule demo, Product tour and Talk to sales. |
| REQ-FOOT-01 | The footer lists the documented product, use case, company, resource, recognition and legal links, security badges and social links. |
| REQ-FORM-01 | The demo and contact forms validate input without being submitted. |
| REQ-LINK-01 | Internal links on the homepage and key pages resolve without client or server errors. |
| REQ-PAGE-01 | Key product, use-case, customer, resource and legal pages load with one h1 and no first-party errors. |
| REQ-RESP-01 | The layout works from phone to desktop width without horizontal overflow. |
| REQ-SEO-01 | Pages expose the expected SEO and social metadata. |
| REQ-A11Y-01 | Basic accessibility: landmarks, image alternatives, keyboard operation, visible focus. |
| REQ-PERF-01 | The homepage becomes usable within reasonable time (informational budget). |

---

## 2. TEST CASES

> Format per test: ID, title, priority, type, confidence, spec reference, viewport, preconditions, numbered steps with concrete targets, and expected observable results. "Link check" means: GET the URL, follow redirects, final status must be below 400 and the final path must not be an error page (title not containing "404" / "Not Found").

### TC-LOAD-001: Homepage loads with correct status, metadata and no runtime errors
- **Priority:** P0 | **Type:** functional | **Confidence:** High | **Spec:** REQ-LOAD-01 | **Viewport:** desktop
- **Preconditions:** fresh browser context, no cookies.
- **Steps:**
  1. Navigate to `https://www.imocha.io/`.
  2. Wait for readiness (see global rules).
  3. Read the HTTP status of the main document, the final URL, `document.title`, `<meta name="description">`, and `<link rel="canonical">`.
  4. Collect uncaught page errors and first-party `console.error` messages during load and for 3 seconds afterwards.
- **Expected:**
  - Main document status is 200 and final URL host is `www.imocha.io`.
  - Title contains "iMocha".
  - Meta description is non-empty and longer than 50 characters.
  - Canonical URL equals `https://www.imocha.io` (trailing slash tolerated).
  - Zero uncaught page errors and zero first-party console errors.
  - Exactly one visible `<h1>` exists and its text is longer than 10 characters.

### TC-NAV-001: Primary navigation shows all documented items on desktop
- **Priority:** P0 | **Type:** functional | **Confidence:** High | **Spec:** REQ-NAV-01 | **Viewport:** desktop
- **Steps:**
  1. Open `/`.
  2. Within the header/navigation landmark, locate the logo link and the items named "Products", "Use Cases", "Customers", "Resources", "Company", "Login" and "Book a Demo".
- **Expected:**
  - All seven named items are visible and not covered by another element.
  - The logo link (image alt contains "iMocha") has `href` equal to `https://www.imocha.io/` or `/`.
  - "Customers" has `href` ending in `/customers`.
  - "Login" has `href` equal to `https://app.imocha.io/` and "Book a Demo" has `href` ending in `/schedule-a-demo`.

### TC-NAV-002: Products menu opens, lists the documented links and closes
- **Priority:** P0 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-NAV-02 | **Viewport:** desktop
- **Steps:**
  1. Open `/`. Hover (or click if hover does nothing) the "Products" nav item.
  2. Wait up to 2 s for the menu panel to become visible.
  3. Read the link names and hrefs in the panel.
  4. Press Escape, then move the pointer to the page body.
- **Expected:**
  - A panel appears containing links with these `href` suffixes: `/skills-intelligence`, `/products/skills-architecture`, `/products/ai-skills-inference`, `/products/skills-assessment`, `/work-intelligence`, `/integrations/imocha-and-workday`, `/integrations/imocha-and-sap-successfactors`, `/integrations/lightcast`, `/integration-partners`.
  - Link names include "Skills Intelligence", "Skills Architecture", "Skills Inference", "Skills Assessment", "Work Intelligence", "Workday", "SAP SuccessFactors", "Lightcast".
  - After Escape or moving away, the panel is no longer visible.

### TC-NAV-003: Use Cases menu lists the six documented destinations
- **Priority:** P1 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-NAV-02 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Open the "Use Cases" menu (hover or click). 3. Read the links.
- **Expected:** links with `href` suffixes `/use-case/skill-gap-analysis`, `/use-case/upskilling-and-reskilling`, `/use-case/internal-mobility`, `/use-case/strategic-workforce-planning`, `/use-case/skills-based-hiring`, `/ai-readiness` are visible with names "Skill Gap Analysis", "Upskilling & Reskilling", "Internal Mobility", "Strategic Workforce Planning", "Skills-based Hiring", "AI-Readiness".

### TC-NAV-004: Resources and Company menus list the documented links
- **Priority:** P1 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-NAV-02 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Open "Resources" and read the links. 3. Close it, open "Company" and read the links.
- **Expected:**
  - Resources contains hrefs ending `/pre-employment-testing/all-tests`, `/blog`, `/resources`, `/webinars`, `/events`.
  - Company contains hrefs ending `/about-us`, `/leadership-and-advisory-board`, `/integration-partners`, `/contactus`, `/careers`, `/newsroom`.
  - Only one menu panel is visible at a time.

### TC-NAV-005: Navigation links navigate to the correct pages
- **Priority:** P0 | **Type:** functional | **Confidence:** High | **Spec:** REQ-NAV-01 | **Viewport:** desktop
- **Steps:** For each of these (open `/` fresh each time, open the menu if needed, click the link): "Customers" -> `/customers`; "About Us" -> `/about-us`; "Contact Us" -> `/contactus`; "Careers" -> `/careers`; "Blogs" -> `/blog`; "Skills Intelligence" -> `/skills-intelligence`.
- **Expected:** after each click the URL path equals the target (redirects to an equivalent canonical path tolerated), the page has one visible `<h1>`, status below 400, and the browser Back button returns to `/`.

### TC-NAV-006: Login button points to the iMocha app and the app responds
- **Priority:** P0 | **Type:** functional | **Confidence:** High | **Spec:** REQ-NAV-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Read the header "Login" link `href`, `target` and `rel`. 3. Link check `https://app.imocha.io/` with a single GET (no credentials, no form interaction).
- **Expected:** `href` equals `https://app.imocha.io/`; if `target="_blank"` then `rel` contains `noopener`; the GET returns a status below 400 and the final host is `app.imocha.io`.

### TC-NAV-007: Announcement banner shows the events message and its link works
- **Priority:** P2 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-NAV-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Locate the top banner containing the text "Meet iMocha at". 3. Click "View Events".
- **Expected:** banner text is visible and not empty; the click leads to a URL whose path is `/events` (query string and the `#upcoming_events` hash tolerated); the events page has one visible `<h1>`.

### TC-NAV-008: Mobile navigation opens, lists items and closes
- **Priority:** P0 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-NAV-03 | **Viewport:** mobile 390x844
- **Steps:**
  1. Open `/` at 390x844.
  2. Confirm the desktop menu items are hidden and a menu (hamburger) button is visible.
  3. Tap the menu button.
  4. Read the visible items; tap "Products" (or its expander) if it is collapsible.
  5. Tap the close control (or the menu button again).
- **Expected:**
  - Hamburger visible and desktop nav items not visible before opening.
  - After opening, "Products", "Use Cases", "Resources", "Company", "Login" and "Book a Demo" are reachable (visible, possibly after scrolling inside the menu).
  - After closing, the menu panel is hidden and the page is scrollable again.
  - No horizontal scroll at any point (`scrollWidth <= innerWidth + 1`).

### TC-CTA-001: Hero "Talk to an Expert" leads to the demo page
- **Priority:** P0 | **Type:** functional | **Confidence:** High | **Spec:** REQ-CTA-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Click the "Talk to an Expert" button in the hero (the first one below the h1). 3. Wait for the new page.
- **Expected:** URL path is `/schedule-a-demo`; page has one visible `<h1>`; a form (or embedded form frame) is visible; status below 400.

### TC-CTA-002: Every demo call to action on the homepage points to the demo page
- **Priority:** P1 | **Type:** functional | **Confidence:** High | **Spec:** REQ-CTA-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Collect all links whose visible text matches "Talk to an Expert", "Book a Demo" or "See How We Did it". 3. Read each `href`.
- **Expected:** at least 6 such links exist; every `href` ends with `/schedule-a-demo`; none is empty or `#`.

### TC-HOME-001: "Look Beyond the Label" section shows three case studies with loaded images
- **Priority:** P1 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-HOME-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to the heading "Look Beyond the Label" until it is in view. 3. Read the case-study captions and the images in the section.
- **Expected:** heading visible; captions mentioning a manufacturing giant, a global IT consulting leader and a Fortune 500 insurer are present; every `<img>` in the section that is in the DOM and not `display:none` has `naturalWidth > 0` after scrolling to it; "Talk to an Expert" button in the section is visible.

### TC-HOME-002: Analyst recognition section lists the three recognitions
- **Priority:** P2 | **Type:** functional | **Confidence:** High | **Spec:** REQ-HOME-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to the heading containing "Leader in Skills Intelligence". 3. Read the cards.
- **Expected:** three recognitions are visible containing the texts "Everest Group", "IDC MarketScape" and "Brandon Hall"; each has a visible logo image with `naturalWidth > 0`; each shows a non-empty description line.

### TC-HOME-003: "Two Intelligences" section explains Work and Skills Intelligence
- **Priority:** P1 | **Type:** functional | **Confidence:** High | **Spec:** REQ-HOME-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to "Two Intelligences, One Defensible View of the Workforce". 3. Read the two sub-sections.
- **Expected:** headings "What is Work Intelligence?" and "What is Skills Intelligence?" are visible; each is followed by at least 200 characters of body text; each has an illustration image with `naturalWidth > 0`; the section's "Talk to an Expert" link points to `/schedule-a-demo`.

### TC-UC-001: The five use-case tabs each show their own content
- **Priority:** P0 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-UC-01 | **Viewport:** desktop
- **Steps:**
  1. Open `/` and scroll to the heading "Every Talent Decision That Matters".
  2. Locate the five use-case selectors: "Skill Gap Analysis", "Upskilling & Reskilling", "Internal Mobility", "Strategic Workforce Planning", "Skills-based Hiring".
  3. Click each selector in order. After each click wait up to 2 s.
  4. After each click read the visible detail heading and the "Learn More" link.
- **Expected:** after the click the detail panel shows (visible, text contains): "Identify Workforce Skill Gaps with Precision"; "Turn Skill Gaps into Targeted Learning Journeys"; "Decode Career Growth from Within"; "Plan Your Future Workforce with Skills Intelligence"; "Hire for Skills, Not Just Resumes". Exactly one detail panel is visible at a time (if the UI is tab-based). Each panel contains a visible image that loaded and a "Learn More" link.
- **Calibration note:** if the section is a stacked list instead of tabs, the test instead asserts that all five detail headings are visible when scrolled to.

### TC-UC-002: Each use-case "Learn More" link resolves to a real page
- **Priority:** P1 | **Type:** functional | **Confidence:** High | **Spec:** REQ-UC-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Read the `href` of each of the five "Learn More" links in the use-case section. 3. Link check each.
- **Expected:** hrefs end with `/use-case/skill-gap-analysis`, `/use-case/upskilling-and-reskilling`, `/use-case/internal-mobility`, a Strategic Workforce Planning link, and `/use-case/skills-based-hiring`; each resolves with status below 400 and a visible h1.
- **Known observation to record (informational):** at the time of writing the Strategic Workforce Planning "Learn More" link was `/blogs/strategic-workforce-planning` (a blog path) while the navigation menu uses `/use-case/strategic-workforce-planning`. The test records both hrefs and reports a low-severity finding if they differ. It does not fail the test as long as the link resolves.

### TC-HOME-004: Partners section shows the eight partner logos and the integrations link
- **Priority:** P2 | **Type:** functional | **Confidence:** High | **Spec:** REQ-HOME-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to "The Context Layer, Connected to Your Tech Ecosystem". 3. Read the logos and the "Explore Integrations" link.
- **Expected:** logos for SAP SuccessFactors, Workday, Oracle, Microsoft, Degreed, Udemy, Jira and Asana are visible with `naturalWidth > 0` (alt text or file name identifies each); "Explore Integrations" has `href` ending `/integration-partners` and that page loads with an h1.

### TC-HOME-005: "Unified System" section shows both intelligence cards
- **Priority:** P2 | **Type:** informational | **Confidence:** Medium | **Spec:** REQ-HOME-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to "The Unified System: Skills & Work Intelligence". 3. Read the two cards and every image inside them.
- **Expected:** headings "Skills Intelligence" and "Work Intelligence" visible with description text; example profile cards (names, skill lists) visible; the central "Context Layer" element visible. Record any image that fails to load or is served from a third-party host (the page hot-links logos from wikimedia, logo.dev and gstatic) as a low-severity finding.

### TC-HOME-006: Customers section shows the heading, two story cards and working links
- **Priority:** P1 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-HOME-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to "Trusted by 300+ Enterprises". 3. Read the story cards and their "Read More" links. 4. Link check each.
- **Expected:** heading visible; story cards titled with "PMI" and "L'Oréal"/"L’Oréal" visible; "Read More" hrefs end with `/customer-stories/pmi-builds-skills-first-talent-development-framework` and `/customer-stories/loreal-transforms-talent-development-by-uncovering-hidden-talent-potential`; both resolve with an h1; video thumbnails are images with `naturalWidth > 0`; if a video play control exists it is not clicked.

### TC-HOME-007: Testimonials show quote, person name, title and logo
- **Priority:** P2 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-HOME-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll through the testimonials area. 3. Read the quotes (if it is a slider, step through it with the next control until all are seen or 6 steps are done).
- **Expected:** at least 3 distinct testimonials are found, each with a non-empty quote and a person name; names include "Fernando Ospina", "Nathalie Clement", "Lynn Hodak", "Sabine van Zanten" (at least three of the four); each has a company logo with `naturalWidth > 0`.

### TC-HOME-008: AI Agents Registry section is present with its call to action
- **Priority:** P2 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-HOME-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to "Meet the Purpose-built Agents Behind the Intelligence". 3. Read the section and its button.
- **Expected:** heading and description visible; "Book a Demo" button has `href` ending `/schedule-a-demo`; if agent cards are present, each has a non-empty title and loaded image.

### TC-HOME-009: "Why iMocha" lists eight capabilities
- **Priority:** P2 | **Type:** functional | **Confidence:** High | **Spec:** REQ-HOME-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to "One Platform, Built for Skills-First Enterprises". 3. Read the card headings.
- **Expected:** these headings are visible, each with a description of at least 30 characters: "Unified Skills Intelligence Layer", "AI-Powered Inference & Validation", "Continuously Accurate Skills Profiles", "Enriched Taxonomies & Ontologies", "Closed-Loop Skills System", "Seamless HR Tech Integration", "Actionable Skills Analytics", "Built for Skills-First Transformation".

### TC-HOME-010: "Get Started Today" call to action leads to the demo page
- **Priority:** P1 | **Type:** functional | **Confidence:** High | **Spec:** REQ-CTA-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to "Unlock Your Workforce Potential". 3. Click its "Talk to an Expert" button.
- **Expected:** heading and 30-minute demo description visible; click opens `/schedule-a-demo` with a visible form.

### TC-FAQ-001: FAQ shows at least 15 questions in an accordion
- **Priority:** P1 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-FAQ-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Scroll to "Frequently Asked Questions". 3. Count the question rows (elements with text starting "Q1." etc.).
- **Expected:** heading visible; at least 15 question rows visible; the first question text contains "identify skill gaps"; initially at most one answer is expanded (answers are collapsed or only the first is open).

### TC-FAQ-002: A FAQ question expands and collapses and exposes its answer
- **Priority:** P0 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-FAQ-01 | **Viewport:** desktop
- **Steps:**
  1. Open `/` and scroll to the FAQ.
  2. Click question "Q2" ("What is skills intelligence and how is it different from traditional talent management?") and wait up to 2 s.
  3. Read the answer region text and the toggle's `aria-expanded` (if present).
  4. Click the same question again and wait up to 2 s.
- **Expected:** after step 2 the answer is visible and contains "skills intelligence" and is longer than 150 characters; `aria-expanded` (if present) is `true`; after step 4 the answer is no longer visible (or `aria-expanded` is `false`). No page navigation happens.

### TC-FAQ-003: Every FAQ question can be opened without errors
- **Priority:** P2 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-FAQ-01 | **Viewport:** desktop
- **Steps:** 1. Open `/` and scroll to the FAQ. 2. For each question in order: click it, wait 500 ms, read the answer length, collapse it if the accordion is multi-open.
- **Expected:** for every question the answer becomes visible with at least 100 characters; zero uncaught page errors; the page does not scroll jump to the top; the total number of questions matches the number found in TC-FAQ-001.

### TC-WIDGET-001: "Get in touch" widget offers the three options
- **Priority:** P1 | **Type:** functional | **Confidence:** Calibrate | **Spec:** REQ-WIDGET-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Locate the floating element containing "Get in touch". 3. Open it (click). 4. Read the options. 5. Click "Schedule demo".
- **Expected:** options "Schedule demo", "Product tour" and "Talk to sales" are visible after opening; "Schedule demo" leads to `/schedule-a-demo` or opens a demo scheduling dialog containing a form or calendar; the widget does not cover the page's primary content when closed.
- **Calibration note:** the first run must record how the widget behaves (link, modal, new tab) and the spec is updated with the observed behaviour.

### TC-FOOT-001: Footer contains every documented link with the right destination
- **Priority:** P1 | **Type:** functional | **Confidence:** High | **Spec:** REQ-FOOT-01 | **Viewport:** desktop
- **Steps:** 1. Open `/` and scroll to the footer. 2. Read all footer links (name + href).
- **Expected:** these footer groups and hrefs exist: Product (`/skills-intelligence`, `/products/skills-architecture`, `/products/ai-skills-inference`, `/work-intelligence`, `/skills-taxonomy`, `/pre-employment-testing/all-tests`, `/products/skills-assessment`); Use cases (the six use-case links); Company (`/about-us`, `/leadership-and-advisory-board`, `/customers`, `/contactus`, `/careers`, `/newsroom`, `/events`); Resources (`/blog`, `/webinars`, `/glossary`, `/roi-through-skills-first-lens`); Recognitions (three links containing `everest`, `idc-marketscape`, `brandon-hall`); Integrations (Workday, SAP SuccessFactors, Lightcast, all partners); legal row (`/security-guidelines`, `/trust-center`, `/privacy-policy`, `/terms-of-service`, `/security/gdpr`, `/sitemap`, `/ai-info`); copyright text contains "iMocha. All rights reserved".

### TC-FOOT-002: Footer security and compliance badges are shown
- **Priority:** P2 | **Type:** functional | **Confidence:** High | **Spec:** REQ-FOOT-01 | **Viewport:** desktop
- **Steps:** 1. Open `/` and scroll to the footer. 2. Read the "Security & compliance" block.
- **Expected:** items "SOC 2 Type II", "ISO 27001:2022" and "GDPR" are visible, each with a badge image with `naturalWidth > 0` and a short description.

### TC-FOOT-003: Social links are correct and safe
- **Priority:** P2 | **Type:** functional | **Confidence:** High | **Spec:** REQ-FOOT-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Read the footer social links (do not navigate to them).
- **Expected:** a LinkedIn link whose host is `www.linkedin.com` and path starts with `/company/imocha`; a YouTube link whose host is `www.youtube.com`; links opening in a new tab have `rel` containing `noopener`.

### TC-FOOT-004: Footer links resolve (same-origin link check)
- **Priority:** P1 | **Type:** functional | **Confidence:** High | **Spec:** REQ-LINK-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Collect all footer links whose host is `www.imocha.io` (de-duplicated). 3. Link check each, 1 request per second.
- **Expected:** every link resolves with status below 400, no redirect chain longer than 3 hops, and no error-page title. Failures list the exact URL and status.

### TC-LEGAL-001: Privacy Policy and Terms of Service pages load
- **Priority:** P2 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-PAGE-01 | **Viewport:** desktop
- **Steps:** 1. Open `/privacy-policy`. 2. Open `/terms-of-service`. 3. Open `/trust-center`. 4. Open `/security-guidelines`.
- **Expected:** each page returns status below 400, has exactly one visible h1 or a clear page title, and its main text is longer than 500 characters; zero first-party errors.

### TC-FORM-001: Demo request form validates empty and invalid input (no submission)
- **Priority:** P0 | **Type:** functional | **Confidence:** Calibrate | **Spec:** REQ-FORM-01 | **Viewport:** desktop
- **Preconditions:** SAFE MODE. Never enter a valid, complete set of data. Never click a final submit with valid data.
- **Steps:**
  1. Open `/schedule-a-demo` and wait for the form (it may be inside an iframe; search same-origin and cross-origin frames).
  2. List the visible fields and mark which are required.
  3. Click the submit button with all fields empty.
  4. Enter `not-an-email` in the email field and a short value in another required field; click submit again.
- **Expected:** at least 3 input fields are visible; after the empty submit, each required field shows validation feedback (native validity message, `aria-invalid`, or visible error text) and the URL does not change to a thank-you page; after the invalid email, the email field is still flagged as invalid; no network request that creates a lead (POST to a form-submission endpoint with a 2xx result) occurs. If the submit cannot be reached without valid data, record the observed field list and mark the validation part as informational.

### TC-FORM-002: Contact page loads and its form validates input (no submission)
- **Priority:** P1 | **Type:** functional | **Confidence:** Calibrate | **Spec:** REQ-FORM-01 | **Viewport:** desktop
- **Steps:** 1. Open `/contactus`. 2. Read the visible contact details and form fields. 3. Submit empty. 4. Enter an invalid email. SAFE MODE as in TC-FORM-001.
- **Expected:** page has one h1; at least one contact detail (address, email or phone) is visible; empty submit produces validation feedback and no thank-you page; invalid email is flagged.

### TC-PAGE-001: All product pages load with one h1 and a demo call to action
- **Priority:** P0 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-PAGE-01 | **Viewport:** desktop
- **Steps:** For each URL: `/skills-intelligence`, `/products/skills-architecture`, `/products/ai-skills-inference`, `/products/skills-assessment`, `/work-intelligence`, `/skills-taxonomy`: open it, wait for readiness, read status, h1, links and console.
- **Expected:** status below 400; exactly one visible h1; at least one link/button whose `href` ends `/schedule-a-demo`; zero first-party errors; page main text longer than 500 characters; no broken (naturalWidth 0) visible same-origin image.

### TC-PAGE-002: All use-case pages and AI readiness page load
- **Priority:** P0 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-PAGE-01 | **Viewport:** desktop
- **Steps:** Open each: `/use-case/skill-gap-analysis`, `/use-case/upskilling-and-reskilling`, `/use-case/internal-mobility`, `/use-case/strategic-workforce-planning`, `/use-case/skills-based-hiring`, `/ai-readiness`.
- **Expected:** same checks as TC-PAGE-001. If `/use-case/strategic-workforce-planning` does not exist (404), record it as a finding with the exact status and mark the test failed (the main navigation links to it).

### TC-PAGE-003: Skills Assessment Library page loads and its search works
- **Priority:** P1 | **Type:** functional | **Confidence:** Calibrate | **Spec:** REQ-PAGE-01 | **Viewport:** desktop
- **Steps:** 1. Open `/pre-employment-testing/all-tests`. 2. Find the search/filter input (if any). 3. Type `Python` and wait up to 3 s. 4. Clear the field.
- **Expected:** the page lists at least 10 assessment/test items; after typing "Python" the visible list changes and the visible items mention Python (or a "no results" state is shown for zero matches); clearing restores a longer list. Read-only: never open paid or sign-up flows. If no search control exists, record that and verify only the list.

### TC-PAGE-004: Blog listing and first article load
- **Priority:** P1 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-PAGE-01 | **Viewport:** desktop
- **Steps:** 1. Open `/blog`. 2. Count article cards (links to `/blog/...`). 3. Click the first article card. 4. Read the article page.
- **Expected:** at least 6 article cards with titles and loaded thumbnails; the article page has one visible h1 matching (contained in) the card title, body text longer than 500 characters, and an author or date indicator if the blog shows one on cards.

### TC-PAGE-005: Customers page lists stories and a story opens
- **Priority:** P1 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-PAGE-01 | **Viewport:** desktop
- **Steps:** 1. Open `/customers`. 2. Count story/customer cards. 3. Open the first story link.
- **Expected:** at least 4 stories or customer logos; the opened story has one h1 and text longer than 500 characters; Back returns to `/customers`.

### TC-PAGE-006: Events, Webinars, Careers, Newsroom, About and Leadership pages load
- **Priority:** P2 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-PAGE-01 | **Viewport:** desktop
- **Steps:** Open each of `/events`, `/webinars`, `/careers`, `/newsroom`, `/about-us`, `/leadership-and-advisory-board`, `/integration-partners`, `/resources`, `/glossary`.
- **Expected:** every page returns a status below 400, has one visible h1 (or clear page title), main text longer than 300 characters, and zero first-party errors.

### TC-LINK-001: Homepage same-origin links resolve
- **Priority:** P1 | **Type:** functional | **Confidence:** High | **Spec:** REQ-LINK-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Collect every `<a href>` whose host is `www.imocha.io`, remove hash-only links and duplicates, cap at 80 links. 3. Link check each at 1 request per second.
- **Expected:** all links resolve with status below 400; none ends on an error-page title; the report lists any redirect chain longer than 2 hops as a low finding; results table shows URL, status and final URL for every link.

### TC-RESP-001: No horizontal overflow and a working layout at four widths
- **Priority:** P1 | **Type:** functional | **Confidence:** High | **Spec:** REQ-RESP-01 | **Viewport:** 1440, 1024, 768, 390
- **Steps:** For each width: 1. Open `/`. 2. Scroll from top to bottom in steps of one screen, waiting 300 ms per step (to trigger lazy loading). 3. Read `document.documentElement.scrollWidth` and `innerWidth`, the bounding box of the h1, and whether the navigation is visible (desktop menu or hamburger).
- **Expected:** at every width `scrollWidth <= innerWidth + 1`; h1 is fully inside the viewport width; either the desktop menu or the hamburger is visible (never both, never neither); no visible image has `naturalWidth` 0 after the scroll.

### TC-SEO-001: Homepage SEO and social metadata present
- **Priority:** P2 | **Type:** functional | **Confidence:** High | **Spec:** REQ-SEO-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Read `<html lang>`, meta viewport, robots meta, `og:title`, `og:description`, `og:image`, `og:type`, `twitter:card`, canonical.
- **Expected:** `lang` attribute is non-empty; viewport contains `width=device-width`; robots meta does not contain `noindex`; `og:title`, `og:description`, `og:image` non-empty; `twitter:card` equals `summary_large_image`; `og:image` URL returns status below 400 and an image content type.

### TC-A11Y-001: Basic accessibility structure and image alternatives
- **Priority:** P2 | **Type:** informational | **Confidence:** High | **Spec:** REQ-A11Y-01 | **Viewport:** desktop
- **Steps:** 1. Open `/`. 2. Check for `header`/`nav`, `main` and `footer` landmarks. 3. List visible `<img>` elements without an `alt` attribute. 4. List `alt` values used more than 3 times. 5. Check every `<button>` and icon-only link has an accessible name.
- **Expected (recorded as findings, never failing):** landmarks present; list of images missing `alt`; list of repeated alt text (the trusted-by logo strip was observed to reuse the alt "Ericsson logo" for different company logos, record this as a low-severity finding if still true); list of unnamed controls.

### TC-A11Y-002: Keyboard users can reach and activate the primary actions
- **Priority:** P1 | **Type:** functional | **Confidence:** Medium | **Spec:** REQ-A11Y-01 | **Viewport:** desktop
- **Steps:** 1. Open `/` and click on the body background once. 2. Press Tab up to 25 times, recording each focused element's name and whether it has a visible focus indicator (outline, ring or style change). 3. Tab to "Book a Demo" and press Enter.
- **Expected:** focus order moves left to right through the header (logo, menu items, Login, Book a Demo); at least 90% of focused elements show a visible focus indicator; pressing Enter on "Book a Demo" navigates to `/schedule-a-demo`; focus never gets trapped (after 25 presses the focused element is still inside the document).

### TC-PERF-001: Homepage becomes usable within the time budget
- **Priority:** P2 | **Type:** informational | **Confidence:** High | **Spec:** REQ-PERF-01 | **Viewport:** desktop
- **Steps:** 1. Open `/` with a cold cache. 2. Record DOMContentLoaded time, time until the h1 is visible, the largest contentful paint (if available), total request count and transferred bytes.
- **Expected (budgets recorded as findings if exceeded, never failing):** h1 visible within 5 s; DOMContentLoaded within 6 s; LCP within 4 s; fewer than 250 requests.

---

## 3. KNOWN OBSERVATIONS (from the page source; verify in the browser)

| # | Observation | Treatment |
|---|---|---|
| 1 | The Strategic Workforce Planning "Learn More" link on the homepage was `/blogs/strategic-workforce-planning`, but navigation uses `/use-case/strategic-workforce-planning`. | Informational finding in TC-UC-002. |
| 2 | The "Trusted by" logo strip reuses the alt text "Ericsson logo" for different logos. | Informational finding in TC-A11Y-001. |
| 3 | The Unified System section hot-links logos from `upload.wikimedia.org`, `img.logo.dev` (URL contains a token) and `encrypted-tbn0.gstatic.com`. These are fragile third-party images. | Informational finding in TC-HOME-005. |
| 4 | FAQ answers are present in the page source (Q1 to Q20). | Used by TC-FAQ-001/002/003. |
| 5 | The "Login" button leads to a different application (`app.imocha.io`). | Only URL and status are checked. |

## 4. OUT OF SCOPE
Authenticated areas (`app.imocha.io`), real form submissions, payment or sign-up flows, load or security testing, cross-browser matrix (Chromium only), and any non-English locale.
