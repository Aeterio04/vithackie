/**
 * Playwright-based crawler for exploring web applications and generating raw app maps.
 * Executed via: npx tsx explore.ts
 */

import { chromium, type Browser, type BrowserContext, type Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

interface HeadingInfo {
  level: number;
  text: string;
}

interface LinkInfo {
  text: string;
  href: string;
}

interface ButtonInfo {
  text: string;
}

interface FieldInfo {
  role: string;
  label: string;
  type: string;
  name: string;
  required: boolean;
}

interface FormInfo {
  id: string;
  action: string;
  method: string;
  submitText: string | null;
  fields: FieldInfo[];
}

interface PageInfo {
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

interface LoginInfo {
  attempted: boolean;
  success: boolean;
  url: string | null;
  note: string | null;
}

interface AppMapStats {
  pagesVisited: number;
  durationSeconds: number;
  budgetHit: 'pages' | 'time' | null;
}

interface AppMapRaw {
  baseUrl: string;
  generatedAt: string;
  login: LoginInfo;
  pages: PageInfo[];
  summary: string;
  features: any[];
  stats: AppMapStats;
  error: string | null;
}

function normalizeUrl(rawUrl: string, baseOrigin: string): { url: string; path: string } | null {
  try {
    const parsed = new URL(rawUrl, baseOrigin);
    if (parsed.origin !== baseOrigin) {
      return null;
    }
    // Drop hash
    parsed.hash = '';
    // Normalize path trailing slash (except root)
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
  return /log\s?out|sign\s?out|delete|remove/i.test(textOrUrl);
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

async function main() {
  const startTime = Date.now();
  const baseUrl = process.env.BASE_URL || 'http://localhost:4000';
  const testUsername = process.env.TEST_USERNAME || '';
  const testPassword = process.env.TEST_PASSWORD || '';
  const maxPages = parseInt(process.env.MAX_PAGES || '10', 10);
  const exploreSeconds = parseInt(process.env.EXPLORE_SECONDS || '90', 10);
  const allowedHostsRaw = process.env.ALLOWED_HOSTS || 'localhost,127.0.0.1';
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
    stats: { pagesVisited: 0, durationSeconds: 0, budgetHit: null },
    error: null,
  };

  let browser: Browser | null = null;
  let currentConsoleErrors: string[] = [];

  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    // 1. Request routing for allowed hosts
    await page.route('**/*', (route) => {
      try {
        const reqUrl = new URL(route.request().url());
        if (!allowedHosts.includes(reqUrl.hostname.toLowerCase())) {
          console.warn(`[Blocked Off-Domain Request] ${reqUrl.hostname}`);
          return route.abort('blockedbyclient');
        }
      } catch {
        return route.abort();
      }
      return route.continue();
    });

    // 2. Error listeners
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        currentConsoleErrors.push(msg.text().slice(0, 300));
      }
    });
    page.on('pageerror', (err) => {
      currentConsoleErrors.push(String(err).slice(0, 300));
    });

    // Helper to scrape current page metadata
    async function scrapeCurrentPage(mainStatus: number = 200): Promise<PageInfo> {
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

      // De-duplicate links up to 40
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
        .$$eval('button, input[type="button"], input[type="submit"]', (elements) =>
          elements.slice(0, 20).map((el) => ({
            text: ((el as HTMLElement).textContent || (el as HTMLInputElement).value || '').trim().slice(0, 50),
          }))
        )
        .catch(() => []);

      const forms: FormInfo[] = await page
        .$$eval('form', (formEls, pagePath) =>
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

              // Accessible label discovery
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

              // ARIA Role determination
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

      const errorsSnapshot = [...currentConsoleErrors].slice(0, 5);
      currentConsoleErrors = []; // Reset for next page

      return {
        url: norm.url,
        path: norm.path,
        title,
        status: mainStatus,
        requiresAuth: false, // Updated post-crawl
        headings,
        links,
        buttons,
        forms,
        consoleErrors: errorsSnapshot,
      };
    }

    // 3. Step 1: Login attempt
    try {
      const initResp = await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 10000 });
      const initStatus = initResp ? initResp.status() : 200;

      // Look for password field on baseUrl, or try /login
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
          } catch {
            // continue candidate checking
          }
        }
      }

      if (hasPasswordField) {
        result.login.attempted = true;
        result.login.url = loginUrl;

        // Record the login page as PageInfo first
        const loginPageInfo = await scrapeCurrentPage(initStatus);
        result.pages.push(loginPageInfo);

        // Fill credentials
        const textOrEmailInput = await page.$('input[type="text"], input[type="email"], input:not([type])');
        if (textOrEmailInput && testUsername) {
          await textOrEmailInput.fill(testUsername);
        }

        const passwordInput = await page.$('input[type="password"]');
        if (passwordInput && testPassword) {
          await passwordInput.fill(testPassword);
        }

        // Submit form
        const submitBtn = await page.$('button[type="submit"], input[type="submit"], form button, button');
        if (submitBtn) {
          await submitBtn.click();
          await page.waitForLoadState('domcontentloaded', { timeout: 5000 }).catch(() => {});
          await new Promise((r) => setTimeout(r, 500));
        }

        // Verify login success: password input gone or url moved away from login path
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

    // Save snapshot after login
    writeOutput(outFile, result);

    // 4. BFS Crawl
    const visitedPaths = new Set<string>();
    for (const p of result.pages) {
      visitedPaths.add(p.path);
    }

    const queue: string[] = [];
    const postLoginNorm = normalizeUrl(page.url(), baseOrigin);
    if (postLoginNorm && !visitedPaths.has(postLoginNorm.path)) {
      queue.push(postLoginNorm.url);
    }
    const baseNorm = normalizeUrl(baseUrl, baseOrigin);
    if (baseNorm && !visitedPaths.has(baseNorm.path) && !queue.includes(baseNorm.url)) {
      queue.push(baseNorm.url);
    }

    while (queue.length > 0) {
      const elapsedSeconds = (Date.now() - startTime) / 1000;
      if (result.pages.length >= maxPages) {
        result.stats.budgetHit = 'pages';
        break;
      }
      if (elapsedSeconds >= exploreSeconds) {
        result.stats.budgetHit = 'time';
        break;
      }

      const nextUrl = queue.shift()!;
      const norm = normalizeUrl(nextUrl, baseOrigin);
      if (!norm) continue;
      if (visitedPaths.has(norm.path)) continue;
      if (norm.path.startsWith('/__')) continue;
      if (isDestructive(norm.path)) continue;

      visitedPaths.add(norm.path);

      try {
        const resp = await page.goto(norm.url, { waitUntil: 'domcontentloaded', timeout: 10000 });
        const status = resp ? resp.status() : 200;
        await new Promise((r) => setTimeout(r, 300));

        const landedNorm = normalizeUrl(page.url(), baseOrigin);
        if (landedNorm && landedNorm.path !== norm.path && visitedPaths.has(landedNorm.path)) {
          // It redirected to an already visited path, skip recording duplicate
          continue;
        }

        const pageInfo = await scrapeCurrentPage(status);
        if (result.pages.some(p => p.path === pageInfo.path)) {
          continue;
        }
        result.pages.push(pageInfo);

        // Progress line for Python wrapper
        console.log(`PAGE ${result.pages.length}/${maxPages} ${pageInfo.path}`);

        // Write progress snapshot
        writeOutput(outFile, result);

        // Enqueue new links
        for (const link of pageInfo.links) {
          if (isDestructive(link.text) || isDestructive(link.href)) continue;
          const linkNorm = normalizeUrl(link.href, baseOrigin);
          if (
            linkNorm &&
            !visitedPaths.has(linkNorm.path) &&
            !linkNorm.path.startsWith('/__') &&
            !queue.includes(linkNorm.url)
          ) {
            queue.push(linkNorm.url);
          }
        }
      } catch (navErr) {
        console.warn(`Error crawling ${norm.path}: ${navErr}`);
      }
    }

    // 5. Post-crawl requiresAuth verification
    const anonContext = await browser.newContext();
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

    if (!result.stats.budgetHit) {
      result.stats.budgetHit = null;
    }
  } catch (err: any) {
    result.error = `Crawler fatal error: ${err.message || String(err)}`;
    console.error(result.error);
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
    result.stats.pagesVisited = result.pages.length;
    result.stats.durationSeconds = Math.round(((Date.now() - startTime) / 1000) * 10) / 10;
    writeOutput(outFile, result);
    console.log(`Crawl finished. Visited ${result.pages.length} pages in ${result.stats.durationSeconds}s.`);
  }
}

main().catch((e) => {
  console.error('Unhandled explore error:', e);
  process.exit(0); // Exit 0 even on partial failure as per CONTRACTS
});
