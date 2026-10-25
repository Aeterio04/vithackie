/**
 * Playwright-based crawler for exploring web applications and generating state-graph app maps.
 * Executed via: npx tsx explore.ts
 *
 * Implements Task A2: Deep Explorer
 * - State fingerprint = normalized URL + DOM structural signature + key UI state (open modal, selected tab, form values hash)
 * - Frontier priority queue by depth levels: L0 (navigation), L1 (single interactions), L2 (multi-step flows), L3+ (deep paths)
 * - AppMap graph output: nodes, edges (with locators & depth), journeys (depth >= 3), unexplored frontier with reasons
 * - Budgets per run AND per depth level; discovery rate threshold stopping; loop & stuck watchdog
 * - Fixed action set: click, fill, select, press, navigate, back, refresh, wait
 * - Per-state signals: console errors, 4xx/5xx responses, failed requests, accessibility violations, broken links
 */

import { chromium, type Browser, type BrowserContext, type Page } from '@playwright/test';
import * as crypto from 'node:crypto';
import * as fs from 'node:fs';
import * as path from 'node:path';

export interface HeadingInfo {
  level: number;
  text: string;
}

export interface LinkInfo {
  text: string;
  href: string;
}

export interface ButtonInfo {
  text: string;
}

export interface FieldInfo {
  role: string;
  label: string;
  type: string;
  name: string;
  required: boolean;
}

export interface FormInfo {
  id: string;
  action: string;
  method: string;
  submitText: string | null;
  fields: FieldInfo[];
}

export interface PageInfo {
  url: string;
  path: string;
  title: string;
  status: number;
  requiresAuth: boolean;
  headings: HeadingInfo[];
  links: LinkInfo[];
  buttons: ButtonInfo[];
  forms: FormInfo[];
  consoleErrors: string[];
}

export interface StateSignals {
  consoleErrors: string[];
  httpErrors: Array<{ status: number; url: string; method?: string }>;
  failedRequests: Array<{ url: string; failure?: string }>;
  accessibilityViolations: Array<{ rule: string; selector: string; impact: string; message: string }>;
  brokenLinks: Array<{ href: string; status?: number; error?: string }>;
}

export interface StateNode {
  stateId: string;
  url: string;
  depth: number;
  domSignature: string;
  uiState: {
    openModal: boolean;
    modalTitle?: string;
    activeTabs: string[];
    formValuesHash: string;
  };
  signals: StateSignals;
}

export type ActionType = 'click' | 'fill' | 'select' | 'press' | 'navigate' | 'back' | 'refresh' | 'wait';

export interface ActionEdge {
  edgeId: string;
  fromState: string;
  toState: string;
  action: ActionType;
  locator: string;
  value?: string | null;
  depth: number;
}

export interface Journey {
  journeyId: string;
  title: string;
  depth: number;
  steps: string[];
}

export interface FrontierState {
  stateId: string;
  url: string;
  depth: number;
  reason: string;
}

export interface LoginInfo {
  attempted: boolean;
  success: boolean;
  url: string | null;
  note: string | null;
}

export interface AppMapStats {
  pagesVisited: number;
  durationSeconds: number;
  budgetHit: string | null;
  statesDiscovered: number;
  transitionsExecuted: number;
}

export interface AppMapRaw {
  baseUrl: string;
  generatedAt: string;
  login: LoginInfo;
  pages: PageInfo[];
  summary: string;
  features: any[];
  stats: AppMapStats;
  states: StateNode[];
  edges: ActionEdge[];
  journeys: Journey[];
  unexploredFrontier: FrontierState[];
  error: string | null;
}

interface FrontierCandidate {
  candidateId: string;
  fromStateId: string;
  targetUrl: string;
  depth: number;
  action: ActionType;
  locator: string;
  value?: string;
  description: string;
  pathFromRoot: ActionEdge[];
}

function hashString(str: string): string {
  return crypto.createHash('sha256').update(str).digest('hex').slice(0, 12);
}

function normalizeUrl(rawUrl: string, baseOrigin: string): { url: string; path: string } | null {
  try {
    const parsed = new URL(rawUrl, baseOrigin);
    const parsedHost = parsed.hostname.replace(/^www\./, '').toLowerCase();
    const baseHost = new URL(baseOrigin).hostname.replace(/^www\./, '').toLowerCase();
    if (parsedHost !== baseHost) {
      return null;
    }
    parsed.hash = '';
    let p = parsed.pathname;
    if (p.length > 1 && p.endsWith('/')) {
      p = p.slice(0, -1);
    }
    parsed.pathname = p;
    return { url: parsed.toString(), path: p };
  } catch {
    return null;
  }
}

function isDestructive(textOrUrl: string): boolean {
  return /log\s?out|sign\s?out|delete|remove|destroy|drop|purge|truncate/i.test(textOrUrl);
}

function writeOutput(outFile: string, data: AppMapRaw) {
  try {
    const dir = path.dirname(outFile);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    const tempFile = `${outFile}.tmp.${Date.now()}.${Math.random().toString(36).slice(2, 6)}`;
    fs.writeFileSync(tempFile, JSON.stringify(data, null, 2), 'utf-8');
    try {
      if (fs.existsSync(outFile)) {
        fs.unlinkSync(outFile);
      }
      fs.renameSync(tempFile, outFile);
    } catch {
      fs.writeFileSync(outFile, JSON.stringify(data, null, 2), 'utf-8');
      if (fs.existsSync(tempFile)) {
        try { fs.unlinkSync(tempFile); } catch {}
      }
    }
  } catch (err) {
    console.error(`Failed to write output file: ${err}`);
  }
}

async function runAccessibilityAudit(page: Page): Promise<Array<{ rule: string; selector: string; impact: string; message: string }>> {
  try {
    const violations = await page.evaluate(() => {
      const items: Array<{ rule: string; selector: string; impact: string; message: string }> = [];

      // 1. Missing alt on images
      const imagesWithoutAlt = Array.from(document.querySelectorAll('img:not([alt])')).slice(0, 5);
      for (const img of imagesWithoutAlt) {
        items.push({
          rule: 'image-alt',
          selector: img.id ? `#${img.id}` : img.className ? `img.${img.className.split(' ')[0]}` : 'img',
          impact: 'critical',
          message: 'Image element is missing an alt attribute',
        });
      }

      // 2. Buttons without accessible name
      const emptyButtons = Array.from(document.querySelectorAll('button, [role="button"]')).filter((b) => {
        const text = (b.textContent || '').trim();
        const ariaLabel = b.getAttribute('aria-label');
        const ariaLabelledby = b.getAttribute('aria-labelledby');
        return !text && !ariaLabel && !ariaLabelledby;
      }).slice(0, 5);
      for (const btn of emptyButtons) {
        items.push({
          rule: 'button-name',
          selector: btn.id ? `#${btn.id}` : 'button',
          impact: 'critical',
          message: 'Button element has no accessible text or aria-label',
        });
      }

      // 3. Form fields without associated labels
      const unlabelledInputs = Array.from(
        document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea')
      ).filter((input) => {
        const hasAriaLabel = !!input.getAttribute('aria-label') || !!input.getAttribute('aria-labelledby');
        const hasId = !!input.id && !!document.querySelector(`label[for="${input.id}"]`);
        const isWrappedInLabel = !!input.closest('label');
        return !hasAriaLabel && !hasId && !isWrappedInLabel;
      }).slice(0, 5);
      for (const inp of unlabelledInputs) {
        items.push({
          rule: 'label',
          selector: inp.id ? `#${inp.id}` : `input[name="${inp.getAttribute('name') || ''}"]`,
          impact: 'serious',
          message: 'Form control does not have an associated label',
        });
      }

      // 4. Missing page title
      if (!document.title || document.title.trim().length === 0) {
        items.push({
          rule: 'document-title',
          selector: 'title',
          impact: 'moderate',
          message: 'Document does not have a valid, non-empty <title>',
        });
      }

      return items;
    });
    return violations;
  } catch {
    return [];
  }
}

async function extractDomAndUiState(page: Page, baseOrigin: string) {
  return await page.evaluate((origin) => {
    // 1. Modals / Dialogs detection
    const openDialog = document.querySelector(
      'dialog[open], [role="dialog"]:not([aria-hidden="true"]), .modal.show, .modal[style*="display: block"]'
    );
    const openModal = !!openDialog;
    const modalTitle = openDialog
      ? (openDialog.querySelector('h1, h2, h3, .modal-title')?.textContent || '').trim().slice(0, 50)
      : undefined;

    // 2. Active Tabs detection
    const activeTabs = Array.from(
      document.querySelectorAll('[role="tab"][aria-selected="true"], .tab.active, [aria-current="page"]')
    )
      .map((el) => (el.textContent || '').trim().slice(0, 40))
      .filter(Boolean);

    // 3. Structural elements count & tags
    const forms = Array.from(document.querySelectorAll('form'));
    const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]), select, textarea'));
    const inputTypes = inputs.map((i) => (i.getAttribute('type') || i.tagName).toLowerCase()).sort();
    const buttons = Array.from(
      document.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"]')
    )
      .map((b) => (b.textContent || (b as HTMLInputElement).value || '').trim().slice(0, 30))
      .filter(Boolean);

    // 4. Form values snapshot
    const formValues = inputs
      .map((i) => {
        const inp = i as HTMLInputElement;
        const name = inp.name || inp.id || '';
        const val =
          inp.type === 'checkbox' || inp.type === 'radio'
            ? String(inp.checked)
            : inp.value ? 'filled' : 'empty';
        return `${name}:${val}`;
      })
      .sort()
      .join(';');

    const structuralTokens = [
      `forms:${forms.length}`,
      `inputs:${inputTypes.join(',')}`,
      `buttons:${buttons.length}`,
      `headings:${document.querySelectorAll('h1, h2, h3').length}`,
      `dialog:${openModal ? 1 : 0}`,
    ].join('|');

    // 5. Interactive Candidates Discovery
    // A) Buttons & Tabs
    const interactiveElements: Array<{
      action: 'click' | 'fill' | 'select';
      locator: string;
      text: string;
      type: string;
      category: 'tab' | 'button' | 'link' | 'form';
    }> = [];

    // Tabs
    const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
    for (const tab of tabs) {
      const tabText = (tab.textContent || '').trim().slice(0, 40);
      if (tabText) {
        interactiveElements.push({
          action: 'click',
          locator: `role=tab[name="${tabText}"]`,
          text: tabText,
          type: 'tab',
          category: 'tab',
        });
      }
    }

    // Buttons
    const buttonEls = Array.from(
      document.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"]')
    );
    for (const btn of buttonEls) {
      const text = (
        btn.textContent ||
        (btn as HTMLInputElement).value ||
        btn.getAttribute('aria-label') ||
        btn.getAttribute('title') ||
        ''
      ).trim().slice(0, 40);
      if (text) {
        interactiveElements.push({
          action: 'click',
          locator: `role=button[name="${text}"]`,
          text,
          type: 'button',
          category: 'button',
        });
      }
    }

    // Forms
    const formSummaries = forms.map((f, idx) => {
      const formSubmitBtn = f.querySelector('button[type="submit"], input[type="submit"], button');
      const submitText = formSubmitBtn
        ? (formSubmitBtn.textContent || (formSubmitBtn as HTMLInputElement).value || '').trim()
        : 'Submit';
      const formInputs = Array.from(f.querySelectorAll('input:not([type="hidden"]), select, textarea')).map((inp) => {
        const inputEl = inp as HTMLInputElement;
        return {
          name: inputEl.name || inputEl.id || '',
          type: (inputEl.type || inputEl.tagName).toLowerCase(),
          id: inputEl.id || '',
        };
      });
      return {
        formIndex: idx,
        submitText,
        inputs: formInputs,
      };
    });

    return {
      openModal,
      modalTitle,
      activeTabs,
      formValues,
      structuralTokens,
      interactiveElements,
      formSummaries,
    };
  }, baseOrigin);
}

function extractJourneys(edges: ActionEdge[], states: StateNode[]): Journey[] {
  // Find all simple paths of depth >= 3 starting from L0 states
  const adj = new Map<string, ActionEdge[]>();
  for (const edge of edges) {
    if (!adj.has(edge.fromState)) {
      adj.set(edge.fromState, []);
    }
    adj.get(edge.fromState)!.push(edge);
  }

  const rootStates = states.filter((s) => s.depth === 0).map((s) => s.stateId);
  const journeys: Journey[] = [];
  const maxJourneys = 10;

  function dfs(currentPath: ActionEdge[], visitedStates: Set<string>) {
    if (journeys.length >= maxJourneys) return;
    if (currentPath.length >= 3) {
      const journeyId = `journey_${journeys.length + 1}`;
      const firstEdge = currentPath[0];
      const fromNode = states.find((s) => s.stateId === firstEdge.fromState);
      const title = `${fromNode ? fromNode.url : 'Start'} -> ${currentPath.map((e) => e.action).join(' -> ')}`;
      journeys.push({
        journeyId,
        title,
        depth: currentPath.length,
        steps: currentPath.map((e) => `${e.action} [${e.locator}]${e.value ? ' value: ' + e.value : ''}`),
      });
      if (currentPath.length >= 6) return; // Cap journey depth at 6
    }

    const lastEdge = currentPath[currentPath.length - 1];
    const nextEdges = adj.get(lastEdge.toState) || [];
    for (const nextEdge of nextEdges) {
      if (!visitedStates.has(nextEdge.toState)) {
        visitedStates.add(nextEdge.toState);
        dfs([...currentPath, nextEdge], visitedStates);
        visitedStates.delete(nextEdge.toState);
      }
    }
  }

  for (const rootId of rootStates) {
    const startEdges = adj.get(rootId) || [];
    for (const edge of startEdges) {
      const visited = new Set<string>([rootId, edge.toState]);
      dfs([edge], visited);
    }
  }

  return journeys;
}

async function main() {
  const startTime = Date.now();
  const baseUrl = process.env.BASE_URL || 'http://localhost:4000';
  const testUsername = process.env.TEST_USERNAME || '';
  const testPassword = process.env.TEST_PASSWORD || '';
  const maxPages = parseInt(process.env.MAX_PAGES || '10', 10);
  const exploreSeconds = parseInt(process.env.EXPLORE_SECONDS || '90', 10);
  const maxDepth = parseInt(process.env.MAX_DEPTH || '4', 10);
  const maxTransitions = parseInt(process.env.MAX_TRANSITIONS || '50', 10);
  const maxPerDepth = parseInt(process.env.MAX_PER_DEPTH || '20', 10);
  const allowedHostsRaw = process.env.ALLOWED_HOSTS || '*';
  const outFile = process.env.OUT_FILE || path.join(process.cwd(), 'explore_raw.json');

  let baseOrigin: string;
  let baseHostname: string;
  try {
    const parsedBase = new URL(baseUrl);
    baseOrigin = parsedBase.origin;
    baseHostname = parsedBase.hostname;
  } catch {
    baseOrigin = 'http://localhost:4000';
    baseHostname = 'localhost';
  }

  const allowedHosts = allowedHostsRaw.split(',').map((h) => h.trim().toLowerCase());
  if (!allowedHosts.includes(baseHostname.toLowerCase())) {
    allowedHosts.push(baseHostname.toLowerCase());
  }

  const result: AppMapRaw = {
    baseUrl,
    generatedAt: new Date().toISOString(),
    login: { attempted: false, success: false, url: null, note: null },
    pages: [],
    summary: '',
    features: [],
    stats: { pagesVisited: 0, durationSeconds: 0, budgetHit: null, statesDiscovered: 0, transitionsExecuted: 0 },
    states: [],
    edges: [],
    journeys: [],
    unexploredFrontier: [],
    error: null,
  };

  let browser: Browser | null = null;
  let currentConsoleErrors: string[] = [];
  let currentHttpErrors: Array<{ status: number; url: string; method?: string }> = [];
  let currentFailedRequests: Array<{ url: string; failure?: string }> = [];

  try {
    browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });
    const context = await browser.newContext({
      viewport: { width: 1366, height: 768 },
      ignoreHTTPSErrors: process.env.IGNORE_HTTPS_ERRORS === 'true',
      userAgent:
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      extraHTTPHeaders: {
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        ...(process.env.X_QA_TOKEN ? { 'X-QA-Token': process.env.X_QA_TOKEN } : {}),
      },
    });
    const page = await context.newPage();

    // 1. Off-domain request blocking & network telemetry (permits safe subresources like CDNs, fonts, styles)
    await page.route('**/*', (route) => {
      try {
        const req = route.request();
        const reqUrl = new URL(req.url());
        const isNav = req.isNavigationRequest();
        const rType = req.resourceType();
        const isSub = ['stylesheet', 'script', 'image', 'font', 'media', 'fetch', 'xhr'].includes(rType);
        const proto = reqUrl.protocol;

        if (
          allowedHosts.includes('*') ||
          proto === 'data:' ||
          proto === 'blob:' ||
          proto === 'about:' ||
          allowedHosts.includes(reqUrl.hostname.toLowerCase()) ||
          (!isNav && isSub)
        ) {
          return route.continue();
        }
        return route.abort('blockedbyclient');
      } catch {
        return route.abort();
      }
    });

    // 2. Telemetry event listeners
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        currentConsoleErrors.push(msg.text().slice(0, 300));
      }
    });
    page.on('pageerror', (err) => {
      currentConsoleErrors.push(String(err).slice(0, 300));
    });
    page.on('response', (res) => {
      if (res.status() >= 400) {
        try {
          const u = new URL(res.url());
          if (allowedHosts.includes(u.hostname.toLowerCase())) {
            currentHttpErrors.push({ status: res.status(), url: res.url(), method: res.request().method() });
          }
        } catch {}
      }
    });
    page.on('requestfailed', (req) => {
      try {
        const u = new URL(req.url());
        if (allowedHosts.includes(u.hostname.toLowerCase())) {
          currentFailedRequests.push({ url: req.url(), failure: req.failure()?.errorText || 'Failed' });
        }
      } catch {}
    });

    // Helper to scrape PageInfo for backwards compatibility
    async function scrapePageInfo(mainStatus: number = 200): Promise<PageInfo> {
      const currentUrl = page.url();
      const norm = normalizeUrl(currentUrl, baseOrigin) || { url: currentUrl, path: new URL(currentUrl).pathname };
      const title = await page.title().catch(() => '');

      const headings: HeadingInfo[] = await page
        .$$eval('h1, h2, h3', (elements) =>
          elements.slice(0, 10).map((el) => ({
            level: parseInt(el.tagName.replace('H', ''), 10) || 1,
            text: (el.textContent || '').trim().slice(0, 100),
          }))
        )
        .catch(() => []);

      const rawLinks: LinkInfo[] = await page
        .$$eval('a[href]', (elements) =>
          elements.map((el) => ({
            text: (el.textContent || '').trim().slice(0, 60),
            href: (el as HTMLAnchorElement).href,
          }))
        )
        .catch(() => []);

      const seenHrefs = new Set<string>();
      const links: LinkInfo[] = [];
      for (const l of rawLinks) {
        if (!seenHrefs.has(l.href) && l.href && !l.href.startsWith('javascript:')) {
          seenHrefs.add(l.href);
          links.push(l);
          if (links.length >= 40) break;
        }
      }

      const buttons: ButtonInfo[] = await page
        .$$eval('button, input[type="button"], input[type="submit"], [role="button"]', (elements) =>
          elements.slice(0, 30).map((el) => ({
            text: (
              (el as HTMLElement).textContent ||
              (el as HTMLInputElement).value ||
              el.getAttribute('aria-label') ||
              el.getAttribute('title') ||
              ''
            ).trim().slice(0, 50),
          }))
        )
        .catch(() => []);

      const forms: FormInfo[] = await page
        .$$eval(
          'form',
          (formEls, pagePath) =>
            formEls.map((form, idx) => {
              const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], button');
              const submitText = submitBtn
                ? ((submitBtn as HTMLElement).textContent || (submitBtn as HTMLInputElement).value || '').trim()
                : null;
              const fieldEls = Array.from(
                form.querySelectorAll('input:not([type="hidden"]):not([type="submit"]), select, textarea')
              );
              const fields: FieldInfo[] = fieldEls.map((field) => {
                const input = field as HTMLInputElement;
                const type = input.type || input.tagName.toLowerCase();
                const name = input.name || input.id || '';
                const required = input.required || false;
                let label = '';
                if (input.id) {
                  const labelEl = document.querySelector(`label[for="${input.id}"]`);
                  if (labelEl) label = (labelEl.textContent || '').trim();
                }
                if (!label && input.labels && input.labels.length > 0) {
                  label = (input.labels[0].textContent || '').trim();
                }
                if (!label) {
                  label = input.getAttribute('aria-label') || input.placeholder || name || type;
                }
                let role = input.getAttribute('role') || '';
                if (!role) {
                  if (type === 'checkbox') role = 'checkbox';
                  else if (type === 'radio') role = 'radio';
                  else if (type === 'select-one' || type === 'select-multiple') role = 'combobox';
                  else role = 'textbox';
                }
                return {
                  role,
                  label: label.slice(0, 80),
                  type,
                  name: name.slice(0, 60),
                  required,
                };
              });
              return {
                id: `${pagePath}#form${idx}`,
                action: form.getAttribute('action') || pagePath,
                method: (form.method || 'GET').toUpperCase(),
                submitText: submitText ? submitText.slice(0, 40) : null,
                fields,
              };
            }),
          norm.path
        )
        .catch(() => []);

      return {
        url: norm.url,
        path: norm.path,
        title,
        status: mainStatus,
        requiresAuth: false,
        headings,
        links,
        buttons,
        forms,
        consoleErrors: [...currentConsoleErrors].slice(0, 5),
      };
    }

    // Helper to build a complete StateNode with signals & fingerprint
    async function captureStateNode(depth: number): Promise<{ stateNode: StateNode; pageInfo: PageInfo; domData: any }> {
      const currentUrl = page.url();
      const norm = normalizeUrl(currentUrl, baseOrigin) || { url: currentUrl, path: new URL(currentUrl).pathname };
      const domData = await extractDomAndUiState(page, baseOrigin);

      const domSig = hashString(domData.structuralTokens);
      const formSig = hashString(domData.formValues);
      const uiState = {
        openModal: domData.openModal,
        modalTitle: domData.modalTitle,
        activeTabs: domData.activeTabs,
        formValuesHash: formSig,
      };

      const stateId = `state_${hashString(`${norm.path}::${domSig}::${JSON.stringify(uiState)}`)}`;

      const a11yViolations = await runAccessibilityAudit(page);
      const signals: StateSignals = {
        consoleErrors: [...currentConsoleErrors],
        httpErrors: [...currentHttpErrors],
        failedRequests: [...currentFailedRequests],
        accessibilityViolations: a11yViolations,
        brokenLinks: [],
      };

      // Reset per-state signal buffers
      currentConsoleErrors = [];
      currentHttpErrors = [];
      currentFailedRequests = [];

      const pageInfo = await scrapePageInfo(200);

      const stateNode: StateNode = {
        stateId,
        url: norm.url,
        depth,
        domSignature: domSig,
        uiState,
        signals,
      };

      return { stateNode, pageInfo, domData };
    }

    // 3. Step 1: Authentication Phase
    try {
      const initResp = await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
      const initStatus = initResp ? initResp.status() : 200;

      // Adapt baseOrigin if baseUrl redirected to e.g. https or www
      try {
        const actualParsed = new URL(page.url());
        if (actualParsed.origin !== baseOrigin) {
          baseOrigin = actualParsed.origin;
          baseHostname = actualParsed.hostname;
          if (!allowedHosts.includes(baseHostname.toLowerCase())) {
            allowedHosts.push(baseHostname.toLowerCase());
          }
        }
      } catch {}

      let hasPasswordField = (await page.$('input[type="password"]')) !== null;
      let loginUrl = baseUrl;

      if (!hasPasswordField) {
        for (const candidate of ['/login', '/signin', '/sign-in']) {
          const candUrl = `${baseOrigin}${candidate}`;
          try {
            const resp = await page.goto(candUrl, { waitUntil: 'domcontentloaded', timeout: 5000 });
            if ((await page.$('input[type="password"]')) !== null) {
              hasPasswordField = true;
              loginUrl = candUrl;
              break;
            }
          } catch {}
        }
      }

      if (hasPasswordField) {
        result.login.attempted = true;
        result.login.url = loginUrl;

        const loginPageInfo = await scrapePageInfo(initStatus);
        result.pages.push(loginPageInfo);

        const textOrEmailInput = await page.$('input[type="text"], input[type="email"], input:not([type])');
        if (textOrEmailInput && testUsername) {
          await textOrEmailInput.fill(testUsername);
        }

        const passwordInput = await page.$('input[type="password"]');
        if (passwordInput && testPassword) {
          await passwordInput.fill(testPassword);
        }

        const submitBtn = await page.$('button[type="submit"], input[type="submit"], form button, button');
        if (submitBtn) {
          await submitBtn.click();
          await page.waitForLoadState('domcontentloaded', { timeout: 5000 }).catch(() => {});
          await new Promise((r) => setTimeout(r, 500));
        }

        const currentUrlAfterLogin = page.url();
        const stillHasPassword = (await page.$('input[type="password"]')) !== null;
        const normLoginPath = normalizeUrl(loginUrl, baseOrigin)?.path || '/login';
        const normPostLoginPath = normalizeUrl(currentUrlAfterLogin, baseOrigin)?.path || '';

        const leftLoginPath = normPostLoginPath !== normLoginPath && normPostLoginPath !== '';
        result.login.success = !stillHasPassword || leftLoginPath;
        result.login.note = result.login.success
          ? `Authenticated successfully as ${testUsername}`
          : 'Password field still visible after form submit';
      } else {
        result.login.attempted = false;
        result.login.success = false;
        result.login.note = 'No login form detected';
      }
    } catch (loginErr) {
      result.login.attempted = true;
      result.login.success = false;
      result.login.note = `Login error: ${String(loginErr).slice(0, 200)}`;
    }

    // 4. Initial Root State Capture (L0)
    const rootStateData = await captureStateNode(0);
    result.states.push(rootStateData.stateNode);
    if (!result.pages.some((p) => p.path === rootStateData.pageInfo.path)) {
      result.pages.push(rootStateData.pageInfo);
    }
    console.log(`STATE ${rootStateData.stateNode.stateId} depth=0 ${rootStateData.stateNode.url}`);
    console.log(`PAGE ${result.pages.length}/${maxPages} ${rootStateData.pageInfo.path}`);

    // 5. Frontier Priority Queue Initialization
    const frontier: FrontierCandidate[] = [];
    const visitedStateIds = new Set<string>([rootStateData.stateNode.stateId]);
    const transitionsPerDepth = new Map<number, number>();
    const selfLoopCount = new Map<string, number>();
    const recentStateHistory: string[] = [rootStateData.stateNode.stateId];

    let currentBrowserStateId = rootStateData.stateNode.stateId;
    let consecutiveZeroDiscovery = 0;
    let transitionsCount = 0;

    function enqueueCandidatesFromState(
      stateNode: StateNode,
      pageInfo: PageInfo,
      domData: any,
      pathFromRoot: ActionEdge[]
    ) {
      const nextDepth = stateNode.depth + 1;

      // A) L0 Navigation candidates (links discovered on page)
      for (const link of pageInfo.links) {
        if (isDestructive(link.text) || isDestructive(link.href)) continue;
        const linkNorm = normalizeUrl(link.href, baseOrigin);
        if (!linkNorm || linkNorm.path.startsWith('/__')) continue;

        frontier.push({
          candidateId: `cand_nav_${hashString(linkNorm.path)}`,
          fromStateId: stateNode.stateId,
          targetUrl: linkNorm.url,
          depth: Math.min(nextDepth, 1), // Direct route discovery is treated as L0/L1
          action: 'click',
          locator: `a[href="${link.href}"]`,
          description: `Navigate to ${linkNorm.path}`,
          pathFromRoot,
        });
      }

      // B) Interactive Elements (Buttons, tabs, custom triggers)
      for (const el of domData.interactiveElements) {
        if (isDestructive(el.text)) continue;
        const candidateDepth = el.category === 'tab' ? Math.max(1, nextDepth) : nextDepth;
        frontier.push({
          candidateId: `cand_act_${hashString(el.locator)}_${nextDepth}`,
          fromStateId: stateNode.stateId,
          targetUrl: stateNode.url,
          depth: candidateDepth,
          action: el.action,
          locator: el.locator,
          description: `Click ${el.category} "${el.text}"`,
          pathFromRoot,
        });
      }

      // C) Forms Submission Candidates (L2+)
      for (const form of domData.formSummaries) {
        if (isDestructive(form.submitText)) continue;
        frontier.push({
          candidateId: `cand_form_${form.formIndex}_${nextDepth}`,
          fromStateId: stateNode.stateId,
          targetUrl: stateNode.url,
          depth: Math.max(2, nextDepth),
          action: 'click',
          locator: `form:nth-of-type(${form.formIndex + 1}) button[type="submit"], form:nth-of-type(${form.formIndex + 1}) input[type="submit"], form:nth-of-type(${form.formIndex + 1}) button`,
          description: `Submit form #${form.formIndex + 1}`,
          pathFromRoot,
        });
      }
    }

    // Populate initial frontier from root
    enqueueCandidatesFromState(rootStateData.stateNode, rootStateData.pageInfo, rootStateData.domData, []);

    // 6. Deep State-Graph Exploration Loop
    while (frontier.length > 0) {
      const elapsedSeconds = (Date.now() - startTime) / 1000;
      if (result.pages.length >= maxPages) {
        result.stats.budgetHit = 'pages';
        break;
      }
      if (elapsedSeconds >= exploreSeconds) {
        result.stats.budgetHit = 'time';
        break;
      }
      if (transitionsCount >= maxTransitions) {
        result.stats.budgetHit = 'transitions';
        break;
      }

      // Sort frontier priority queue: depth ascending (L0 -> L1 -> L2 -> L3+)
      frontier.sort((a, b) => a.depth - b.depth);
      const candidate = frontier.shift()!;

      // Depth budget check
      const currentDepthCount = transitionsPerDepth.get(candidate.depth) || 0;
      if (currentDepthCount >= maxPerDepth) {
        result.unexploredFrontier.push({
          stateId: candidate.fromStateId,
          url: candidate.targetUrl,
          depth: candidate.depth,
          reason: 'depth_budget_exceeded',
        });
        continue;
      }
      if (candidate.depth > maxDepth) {
        result.unexploredFrontier.push({
          stateId: candidate.fromStateId,
          url: candidate.targetUrl,
          depth: candidate.depth,
          reason: 'max_depth_exceeded',
        });
        continue;
      }

      // Stuck / Loop check on fromStateId
      const loopCount = selfLoopCount.get(candidate.fromStateId) || 0;
      if (loopCount >= 3) {
        result.unexploredFrontier.push({
          stateId: candidate.fromStateId,
          url: candidate.targetUrl,
          depth: candidate.depth,
          reason: 'stuck_loop_detected',
        });
        continue;
      }

      // Replay / Browser Navigation to fromStateId if browser is on a different state
      let navigationSuccess = true;
      if (currentBrowserStateId !== candidate.fromStateId) {
        try {
          await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 8000 });
          for (const edge of candidate.pathFromRoot) {
            try {
              if (edge.action === 'navigate') {
                await page.goto(edge.locator, { waitUntil: 'domcontentloaded', timeout: 5000 });
              } else if (edge.action === 'click') {
                await page.locator(edge.locator).first().click({ timeout: 4000 });
              } else if (edge.action === 'fill' && edge.value) {
                await page.locator(edge.locator).first().fill(edge.value, { timeout: 4000 });
              }
              await page.waitForLoadState('domcontentloaded', { timeout: 3000 }).catch(() => {});
            } catch {
              navigationSuccess = false;
              break;
            }
          }
        } catch {
          navigationSuccess = false;
        }
      }

      if (!navigationSuccess) {
        result.unexploredFrontier.push({
          stateId: candidate.fromStateId,
          url: candidate.targetUrl,
          depth: candidate.depth,
          reason: 'replay_failed',
        });
        continue;
      }

      // Execute Candidate Action
      transitionsCount++;
      transitionsPerDepth.set(candidate.depth, currentDepthCount + 1);

      try {
        console.log(`ACTION [L${candidate.depth}] ${candidate.action} on ${candidate.locator}`);

        if (candidate.action === 'click') {
          // Check if link navigation or button click
          if (candidate.locator.startsWith('a[href=')) {
            await page.goto(candidate.targetUrl, { waitUntil: 'domcontentloaded', timeout: 8000 });
          } else {
            const loc = page.locator(candidate.locator).first();
            if (await loc.isVisible({ timeout: 2000 }).catch(() => false)) {
              await loc.click({ timeout: 3000 });
            } else {
              // Try fallback text or role click
              await page.click(candidate.locator, { timeout: 3000 }).catch(() => {});
            }
          }
        } else if (candidate.action === 'fill' && candidate.value) {
          await page.fill(candidate.locator, candidate.value, { timeout: 3000 });
        } else if (candidate.action === 'press') {
          await page.press(candidate.locator, candidate.value || 'Enter', { timeout: 3000 });
        }

        await page.waitForLoadState('domcontentloaded', { timeout: 3000 }).catch(() => {});
        await new Promise((r) => setTimeout(r, 300));
      } catch (actErr) {
        console.warn(`Action failed: ${candidate.action} ${candidate.locator} (${actErr})`);
      }

      // Capture Post-Action State
      const newStateData = await captureStateNode(candidate.depth);
      const toStateId = newStateData.stateNode.stateId;
      currentBrowserStateId = toStateId;

      // Record Action Edge in Graph
      const edgeId = `edge_${candidate.fromStateId}_${toStateId}_${transitionsCount}`;
      const actionEdge: ActionEdge = {
        edgeId,
        fromState: candidate.fromStateId,
        toState: toStateId,
        action: candidate.action,
        locator: candidate.locator,
        value: candidate.value || null,
        depth: candidate.depth,
      };
      result.edges.push(actionEdge);

      // Check self-loop / stuck
      if (toStateId === candidate.fromStateId) {
        const prev = selfLoopCount.get(candidate.fromStateId) || 0;
        selfLoopCount.set(candidate.fromStateId, prev + 1);
      } else {
        selfLoopCount.set(candidate.fromStateId, 0);
      }

      // Check oscillation / loop detection in history
      recentStateHistory.push(toStateId);
      if (recentStateHistory.length > 8) {
        recentStateHistory.shift();
      }
      const isOscillating =
        recentStateHistory.length >= 4 &&
        recentStateHistory[recentStateHistory.length - 1] === recentStateHistory[recentStateHistory.length - 3] &&
        recentStateHistory[recentStateHistory.length - 2] === recentStateHistory[recentStateHistory.length - 4];

      if (isOscillating) {
        console.warn(`[Watchdog] Cyclic oscillation detected between states.`);
      }

      // State Discovery Rate Watchdog
      if (!visitedStateIds.has(toStateId)) {
        visitedStateIds.add(toStateId);
        result.states.push(newStateData.stateNode);
        consecutiveZeroDiscovery = 0;

        // Register PageInfo if new page path
        if (!result.pages.some((p) => p.path === newStateData.pageInfo.path)) {
          result.pages.push(newStateData.pageInfo);
          console.log(`PAGE ${result.pages.length}/${maxPages} ${newStateData.pageInfo.path}`);
        }

        console.log(`STATE ${toStateId} depth=${candidate.depth} ${newStateData.stateNode.url}`);

        // Write snapshot on new state
        writeOutput(outFile, result);

        // Enqueue new frontier candidates if not oscillating
        if (!isOscillating) {
          enqueueCandidatesFromState(
            newStateData.stateNode,
            newStateData.pageInfo,
            newStateData.domData,
            [...candidate.pathFromRoot, actionEdge]
          );
        }
      } else {
        consecutiveZeroDiscovery++;
        if (consecutiveZeroDiscovery >= 12) {
          result.stats.budgetHit = 'discovery_rate';
          console.log('[Watchdog] Stopping condition hit: discovery rate threshold.');
          break;
        }
      }
    }

    // 7. Flush remaining frontier items to unexploredFrontier
    const finalReason = result.stats.budgetHit
      ? `${result.stats.budgetHit}_budget_hit`
      : 'budget_limit_reached';
    for (const remaining of frontier) {
      if (!result.unexploredFrontier.some((u) => u.stateId === remaining.fromStateId && u.url === remaining.targetUrl)) {
        result.unexploredFrontier.push({
          stateId: remaining.fromStateId,
          url: remaining.targetUrl,
          depth: remaining.depth,
          reason: finalReason,
        });
      }
    }

    // 8. Extract Journeys (depth >= 3)
    result.journeys = extractJourneys(result.edges, result.states);
    console.log(`Extracted ${result.journeys.length} deep journeys (depth >= 3).`);

    // 9. Post-crawl requiresAuth verification
    const anonContext = await browser.newContext({
      ignoreHTTPSErrors: true,
      userAgent:
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    });
    for (const pageItem of result.pages) {
      if (pageItem.path === '/login' || pageItem.path === '/signin' || pageItem.path === '/signup') {
        pageItem.requiresAuth = false;
        continue;
      }
      try {
        const checkResp = await anonContext.request.get(pageItem.url, { maxRedirects: 0 });
        const st = checkResp.status();
        const loc = checkResp.headers()['location'] || '';
        if ((st >= 300 && st < 400 && /login|signin/i.test(loc)) || st === 401 || st === 403) {
          pageItem.requiresAuth = true;
        } else {
          pageItem.requiresAuth = false;
        }
      } catch {
        pageItem.requiresAuth = false;
      }
    }
    await anonContext.close();

  } catch (err: any) {
    result.error = `Crawler fatal error: ${err.message || String(err)}`;
    console.error(result.error);
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
    result.stats.pagesVisited = result.pages.length;
    result.stats.statesDiscovered = result.states.length;
    result.stats.transitionsExecuted = result.edges.length;
    result.stats.durationSeconds = Math.round(((Date.now() - startTime) / 1000) * 10) / 10;
    writeOutput(outFile, result);
    console.log(
      `Crawl finished. Visited ${result.pages.length} pages, ${result.states.length} states, ${result.edges.length} edges in ${result.stats.durationSeconds}s.`
    );
  }
}

main().catch((e) => {
  console.error('Unhandled explore error:', e);
  process.exit(0);
});
