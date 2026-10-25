/**
 * Spec-driven test harness.
 *
 * One Playwright test per spec TC. Every spec step is wrapped in
 * test.step('<n>: <step text>') and every Expected line is evaluated
 * individually (expected vs actual recorded in tc_result.json).
 * Read-only guard, shared request limiter and link checker live here.
 */
import { test, expect } from '../fixtures';
import type { Page, BrowserContext, APIRequestContext, Locator, Response } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';

export const BASE = process.env.SPEC_BASE_URL || 'https://www.imocha.io';
// +100 ms margin so no sliding 1 s window ever holds more than MAX_RPS gated requests (log jitter included)
const MIN_GAP_MS = Math.ceil(1000 / Number(process.env.MAX_RPS || 2)) + 100;
const RATE_DIR = process.env.RATE_DIR || path.join(process.cwd(), '.rate');
const RATE_LOG = process.env.RATE_LOG || path.join(RATE_DIR, 'requests.jsonl');

// ---------------------------------------------------------------- noise / first party
export const NOISE = (process.env.NOISE_RE ||
  'googletagmanager|google-analytics|doubleclick|facebook|linkedin|hotjar|clarity|hubspot|hs-scripts|cookiebot|onetrust|intercom|drift|6sense|clearbit|zoominfo|bing|adroll|favicon|hsforms|hs-analytics|hs-banner|hsadspixel|licdn|ads\\.|gstatic|g\\.co');
const NOISE_RE = new RegExp(NOISE, 'i');
const FIRST_PARTY_RE = /(^|\.)imocha\.io$|(^|\.)website-files\.com$/i;
const SUBMIT_RE = /hsforms|forms\.hubspot|formspree|form-submissions|\/api\/v1\/form|\/submit(\b|\/|\?)|\/forms?\/(submit|api)/i;

export function isFirstParty(url: string): boolean {
  try { return FIRST_PARTY_RE.test(new URL(url).hostname); } catch { return false; }
}
export const isNoise = (s: string) => NOISE_RE.test(s);

// ---------------------------------------------------------------- shared limiter (cross-worker)
function sleep(ms: number) { return new Promise((r) => setTimeout(r, ms)); }

export async function throttle(kind: string, url: string): Promise<void> {
  fs.mkdirSync(RATE_DIR, { recursive: true });
  const lock = path.join(RATE_DIR, 'lock');
  const slotFile = path.join(RATE_DIR, 'slot.txt');
  let fd = -1;
  for (let i = 0; i < 600; i++) {
    try { fd = fs.openSync(lock, 'wx'); break; } catch {
      try { if (Date.now() - fs.statSync(lock).mtimeMs > 5000) fs.unlinkSync(lock); } catch {}
      await sleep(15 + Math.random() * 20);
    }
  }
  let waitMs = 0;
  try {
    let last = 0;
    try { last = Number(fs.readFileSync(slotFile, 'utf-8')) || 0; } catch {}
    const now = Date.now();
    const slot = Math.max(now, last + MIN_GAP_MS);
    fs.writeFileSync(slotFile, String(slot));
    waitMs = slot - now;
  } finally {
    if (fd >= 0) { try { fs.closeSync(fd); fs.unlinkSync(lock); } catch {} }
  }
  if (waitMs > 0) await sleep(waitMs);
  try { fs.appendFileSync(RATE_LOG, JSON.stringify({ ts: Date.now(), kind, url, pid: process.pid }) + '\n'); } catch {}
}

// ---------------------------------------------------------------- types
export interface Finding { severity: 'info' | 'low' | 'medium' | 'high'; title: string; detail: string; observation?: number }
export interface TcMeta {
  id: string; title: string; type: 'functional' | 'informational'; priority: string;
  steps: string[]; expected: string[]; timeoutMs?: number; allowSubmitClicks?: boolean;
}
export interface Ctx {
  page: Page; context: BrowserContext; request: APIRequestContext; meta: TcMeta;
  st: Record<string, any>; findings: Finding[]; notes: string[];
  consoleErrors: string[]; pageErrors: string[]; nonGet: Array<{ method: string; url: string; blocked: boolean; status?: number }>;
  mainStatus: number | null;
  goto(p: string, opts?: { noReady?: boolean }): Promise<Response | null>;
  ready(): Promise<void>;
  exp(cond: boolean, actual: string): void;
  finding(f: Finding): void;
  linkCheck(url: string, opts?: { maxHops?: number }): Promise<LinkResult>;
  caption(text: string): Promise<void>;
}
export type StepFn = (c: Ctx) => Promise<void>;
export type ExpFn = (c: Ctx) => Promise<string | void>;
export interface TcImpl { steps: StepFn[]; expected: ExpFn[] }

export class SiteAssertion extends Error { kind = 'assertion'; }

export interface LinkResult { url: string; status: number; finalUrl: string; hops: number; title: string; ok: boolean; hasH1: boolean; error?: string }

// ---------------------------------------------------------------- text helpers
export const norm = (s: string) => (s || '').replace(/[​ ]/g, ' ').replace(/\s+/g, ' ').trim();
export function looseRe(text: string): RegExp {
  const toks = text.split(/[^A-Za-z0-9À-ɏ]+/).filter(Boolean);
  return new RegExp(toks.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[^A-Za-z0-9\\u00c0-\\u024f]+'), 'i');
}
export const absUrl = (href: string, base = BASE + '/') => { try { return new URL(href, base).toString(); } catch { return href; } };
export const pathOf = (href: string) => { try { const u = new URL(href, BASE + '/'); return u.pathname.replace(/\/+$/, '') || '/'; } catch { return href; } };
export const endsWithPath = (href: string | null | undefined, suffix: string) => !!href && pathOf(href).endsWith(suffix.replace(/\/+$/, ''));

// ---------------------------------------------------------------- page helpers
export function heading(page: Page, text: string): Locator {
  return page.locator('h1,h2,h3,h4').filter({ hasText: looseRe(text) }).first();
}
export function sectionOf(h: Locator): Locator {
  return h.locator('xpath=ancestor::section[1]');
}
/** Wait until an element's height stops changing (accordion / tab animation finished). */
export async function settled(loc: Locator, maxMs = 4000) {
  let last = -1, same = 0; const t0 = Date.now();
  while (Date.now() - t0 < maxMs && same < 3) {
    const h = await loc.evaluate((e) => e.getBoundingClientRect().height).catch(() => -2);
    same = h === last ? same + 1 : 0; last = h;
    await new Promise((r) => setTimeout(r, 150));
  }
}
/** Attribute without the implicit wait for a missing element. */
export async function attr(loc: Locator, name: string): Promise<string | null> {
  if (!(await loc.count())) return null;
  return loc.first().getAttribute(name, { timeout: 1000 }).catch(() => null);
}
/** Readable main text of the page: <main> if present, else <body>. No implicit waits. */
export async function mainText(page: Page): Promise<string> {
  return norm(await page.evaluate(() => ((document.querySelector('main') as HTMLElement | null) ?? document.body).innerText));
}
/** Click a link so that it opens in the same tab (the site opens some links with target=_blank). */
export async function clickSameTab(loc: Locator) {
  await loc.evaluate((e) => { (e as HTMLAnchorElement).target = '_self'; }).catch(() => {});
  await loc.click({ timeout: 8000 });
}
export async function visibleCount(loc: Locator): Promise<number> {
  const n = await loc.count();
  let v = 0;
  for (let i = 0; i < n; i++) if (await loc.nth(i).isVisible().catch(() => false)) v++;
  return v;
}
export async function scrollTo(loc: Locator) {
  await loc.scrollIntoViewIfNeeded({ timeout: 10000 }).catch(() => {});
  await loc.page().waitForTimeout(350);
}
/** Scroll the whole page top to bottom to trigger lazy loading / reveal animations. */
export async function scrollThrough(page: Page, pauseMs = 250) {
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  const vh = page.viewportSize()?.height ?? 900;
  for (let y = 0; y < h; y += vh) { await page.evaluate((yy) => window.scrollTo(0, yy), y); await page.waitForTimeout(pauseMs); }
  await page.evaluate(() => window.scrollTo(0, 0));
}
/** Visible <img> elements within scope with their load state after scrolling to each. */
export async function imageState(scope: Locator, waitMs = 8000) {
  const imgs = scope.locator('img');
  const n = await imgs.count();
  const out: Array<{ src: string; alt: string; visible: boolean; loaded: boolean; w: number; host: string }> = [];
  for (let i = 0; i < n; i++) {
    const im = imgs.nth(i);
    const disp = await im.evaluate((e) => { const s = getComputedStyle(e); const r = e.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && (r.width > 0 || r.height > 0 || (e as HTMLImageElement).complete); }).catch(() => false);
    if (!disp) continue;
    await im.scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => {});
    const t0 = Date.now();
    let w = 0, complete = false;
    while (Date.now() - t0 < waitMs) {
      const r = await im.evaluate((e) => ({ w: (e as HTMLImageElement).naturalWidth, c: (e as HTMLImageElement).complete })).catch(() => ({ w: 0, c: false }));
      w = r.w; complete = r.c;
      if (w > 0) break;
      await new Promise((r2) => setTimeout(r2, 250));
    }
    const src = (await im.evaluate((e) => (e as HTMLImageElement).currentSrc || (e as HTMLImageElement).src).catch(() => '')) || '';
    out.push({ src, alt: (await im.getAttribute('alt').catch(() => '')) || '', visible: await im.isVisible().catch(() => false), loaded: w > 0, w, host: (() => { try { return new URL(src).hostname; } catch { return ''; } })() });
  }
  return out;
}
export async function linksIn(scope: Locator): Promise<Array<{ text: string; href: string; target: string; rel: string; visible: boolean }>> {
  return scope.locator('a[href]').evaluateAll((as) => as.map((a) => {
    const el = a as HTMLAnchorElement; const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    const txt = (el.innerText || el.getAttribute('aria-label') || el.querySelector('img')?.getAttribute('alt') || '').replace(/[​\s]+/g, ' ').trim();
    return { text: txt, href: el.getAttribute('href') || '', target: el.target || '', rel: el.rel || '', visible: r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' };
  }));
}
export async function notCovered(loc: Locator): Promise<boolean> {
  return loc.evaluate((e) => {
    const r = e.getBoundingClientRect(); if (r.width === 0 || r.height === 0) return false;
    const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
    const t = document.elementFromPoint(x, y); return !!t && (e === t || e.contains(t) || t.contains(e));
  }).catch(() => false);
}
export async function overflow(page: Page) {
  return page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
}

// ---------------------------------------------------------------- menu helpers (Webflow dropdowns)
export function dropdown(page: Page, name: string): { wrap: Locator; toggle: Locator; panel: Locator } {
  const wrap = page.locator('.w-dropdown').filter({ has: page.locator('.w-dropdown-toggle').filter({ hasText: new RegExp('^\\s*' + name + '\\s*$', 'i') }) }).first();
  return { wrap, toggle: wrap.locator('.w-dropdown-toggle').first(), panel: wrap.locator('.w-dropdown-list').first() };
}
/** Hover first; if the panel does not open, click. Returns how it opened. */
export async function openMenu(page: Page, name: string): Promise<'hover' | 'click'> {
  const { toggle, panel } = dropdown(page, name);
  await toggle.scrollIntoViewIfNeeded().catch(() => {});
  await toggle.hover({ timeout: 8000 });
  try { await panel.waitFor({ state: 'visible', timeout: 3000 }); return 'hover'; } catch {}
  await toggle.click({ timeout: 8000 });
  await panel.waitFor({ state: 'visible', timeout: 4000 });
  return 'click';
}
export async function closeMenus(page: Page) {
  await page.keyboard.press('Escape').catch(() => {});
  await page.mouse.move(700, 600).catch(() => {});
  await page.waitForTimeout(600);
  const open = page.locator('.w-dropdown-toggle.w--open');
  const n = await open.count();
  for (let i = 0; i < n; i++) { await open.nth(i).click({ timeout: 2000 }).catch(() => {}); }
  await page.waitForTimeout(400);
}
export async function panelLinks(page: Page, name: string) {
  const { panel } = dropdown(page, name);
  return linksIn(panel);
}

// ---------------------------------------------------------------- result file
export function writeResult(testInfoAttach: (n: string, body: string) => Promise<void>, data: any) {
  return testInfoAttach('tc_result.json', JSON.stringify(data, null, 2));
}

// ---------------------------------------------------------------- the harness
export function runTc(meta: TcMeta, impl: TcImpl) {
  test(`${meta.id}: ${meta.title}`, async ({ page, context, request }, testInfo) => {
    test.setTimeout(meta.timeoutMs ?? 90000);
    const startedAt = Date.now();
    const c: Ctx = {
      page, context, request, meta, st: {}, findings: [], notes: [], consoleErrors: [], pageErrors: [], nonGet: [], mainStatus: null,
      async goto(p, opts) {
        const url = p.startsWith('http') ? p : BASE + p;
        await throttle('navigate', url);
        const r = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
        c.mainStatus = r ? r.status() : null;
        if (!opts?.noReady) await c.ready();
        return r;
      },
      async ready() {
        await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
        await page.locator('h1').first().waitFor({ state: 'visible', timeout: 20000 }).catch(() => {});
        const t0 = Date.now(); let last = -1, since = Date.now();
        while (Date.now() - t0 < 8000) {
          const h = await page.evaluate(() => document.documentElement.scrollHeight).catch(() => 0);
          if (h !== last) { last = h; since = Date.now(); } else if (Date.now() - since >= 500) break;
          await page.waitForTimeout(100);
        }
        const ov = await dismissOverlays(page);
        if (ov) c.notes.push(`overlay handled: ${ov}`);
      },
      exp(cond, actual) { if (!cond) throw new SiteAssertion(actual); },
      finding(f) { c.findings.push(f); },
      async linkCheck(url, opts) { return linkCheck(request, url, opts?.maxHops ?? 6); },
      async caption(text) { await setCaption(page, text); },
    };

    // missing elements must fail fast (a 30 s implicit wait per absent locator was the main time sink)
    page.setDefaultTimeout(8000);
    page.setDefaultNavigationTimeout(30000);
    // consent banner appears late (after scroll/idle): dismiss it whenever it shows up, never accept tracking
    await context.addInitScript(() => {
      if (window !== window.top) return;
      const iv = setInterval(() => {
        const b = document.getElementById('hs-eu-decline-button');
        if (b && (b as HTMLElement).offsetParent) { (b as HTMLElement).click(); (window as any).__overlayDismissed = 'hs-eu-decline-button'; }
      }, 300);
      setTimeout(() => clearInterval(iv), 60000);
    });
    // --- collectors
    const onConsole = (m: any) => {
      if (m.type() !== 'error') return;
      const loc = m.location?.()?.url || ''; const txt = m.text();
      if (isNoise(loc) || isNoise(txt)) return;
      if (isFirstParty(loc)) c.consoleErrors.push(`${loc}: ${txt}`.slice(0, 300));
    };
    const attach = (p: Page) => {
      p.on('console', onConsole);
      p.on('pageerror', (e) => { c.pageErrors.push(String(e.message || e).slice(0, 300)); });
      p.on('domcontentloaded', () => { if (c.st.__caption) setCaption(p, c.st.__caption).catch(() => {}); });
    };
    attach(page);
    context.on('page', attach);
    context.on('request', (r) => {
      if (r.method() !== 'GET' && r.method() !== 'HEAD' && r.method() !== 'OPTIONS') {
        const rec = { method: r.method(), url: r.url().slice(0, 200), blocked: false } as any;
        c.nonGet.push(rec);
      }
    });
    context.on('response', (r) => {
      const m = r.request().method();
      if (m !== 'GET' && m !== 'HEAD' && m !== 'OPTIONS') {
        const rec = c.nonGet.find((x) => x.url === r.url().slice(0, 200) && x.status === undefined);
        if (rec) rec.status = r.status();
      }
    });
    // --- read-only guard (registered after fixture route => runs first)
    const safety: string[] = [];
    await context.route('**/*', async (route) => {
      const req = route.request(); const m = req.method(); const u = req.url();
      if (m === 'GET' || m === 'HEAD' || m === 'OPTIONS') return route.fallback();
      const first = isFirstParty(u);
      const looksSubmit = SUBMIT_RE.test(u);
      if (first || looksSubmit) {
        safety.push(`${m} ${u.slice(0, 160)}`);
        const rec = c.nonGet.find((x) => x.url === u.slice(0, 200) && !x.blocked); if (rec) rec.blocked = true;
        return route.abort('blockedbyclient');
      }
      return route.fallback(); // third-party analytics noise
    });

    // --- steps
    const stepResults: any[] = [];
    const expectedResults: any[] = [];
    let stepFailure: Error | null = null;
    if (impl.steps.length !== meta.steps.length) {
      throw new Error(`HARNESS: implementation has ${impl.steps.length} steps but spec ${meta.id} has ${meta.steps.length}`);
    }
    if (impl.expected.length !== meta.expected.length) {
      throw new Error(`HARNESS: implementation has ${impl.expected.length} expected checks but spec ${meta.id} has ${meta.expected.length}`);
    }
    for (let i = 0; i < meta.steps.length; i++) {
      const label = `${i + 1}: ${meta.steps[i]}`;
      const t0 = Date.now();
      if (stepFailure) { stepResults.push({ n: i + 1, text: meta.steps[i], status: 'skipped', ms: 0 }); continue; }
      try {
        await test.step(label, async () => {
          c.st.__caption = `${meta.id}  step ${label}`.slice(0, 160);
          await setCaption(page, c.st.__caption);
          await impl.steps[i](c);
        });
        stepResults.push({ n: i + 1, text: meta.steps[i], status: 'passed', ms: Date.now() - t0 });
      } catch (e: any) {
        stepFailure = e;
        stepResults.push({ n: i + 1, text: meta.steps[i], status: 'failed', ms: Date.now() - t0, error: String(e.message || e).slice(0, 400), kind: e instanceof SiteAssertion ? 'assertion' : 'execution' });
      }
    }
    // --- expected
    for (let i = 0; i < meta.expected.length; i++) {
      if (stepFailure) { expectedResults.push({ n: i + 1, text: meta.expected[i], status: 'not_evaluated', actual: 'a step failed before this check' }); continue; }
      try {
        await test.step(`Expected ${i + 1}: ${meta.expected[i]}`.slice(0, 200), async () => {
          c.st.__caption = `${meta.id}  expected ${i + 1}`;
          await setCaption(page, `${meta.id}  expected: ${meta.expected[i]}`.slice(0, 160));
          const actual = await impl.expected[i](c);
          expectedResults.push({ n: i + 1, text: meta.expected[i], status: 'passed', actual: actual || 'ok' });
        });
      } catch (e: any) {
        expectedResults.push({ n: i + 1, text: meta.expected[i], status: 'failed', actual: String(e.message || e).slice(0, 500), kind: e instanceof SiteAssertion ? 'assertion' : 'execution' });
      }
    }
    // --- safety
    const safetyViolations = meta.allowSubmitClicks ? [] : safety;
    const submitted2xx = c.nonGet.filter((x) => !x.blocked && x.status !== undefined && x.status < 300 && (isFirstParty(x.url) || SUBMIT_RE.test(x.url)));
    const failed = expectedResults.filter((e) => e.status === 'failed');
    const execFail = stepResults.find((s) => s.status === 'failed') || failed.find((e) => e.kind === 'execution');
    let status: string;
    if (safetyViolations.length || submitted2xx.length) status = 'safety_violation';
    else if (meta.type === 'informational') {
      for (const f of failed) c.findings.push({ severity: 'low', title: `Expectation not met: ${f.text.slice(0, 80)}`, detail: f.actual });
      if (stepFailure) c.findings.push({ severity: 'info', title: 'Step could not be completed', detail: String(stepFailure.message).slice(0, 300) });
      status = c.findings.length ? 'passed_with_issues' : 'passed';
    } else if (execFail) status = 'script_error';
    else if (failed.length) status = 'failed';
    else status = 'passed';

    const result = {
      id: meta.id, title: meta.title, type: meta.type, priority: meta.priority, status,
      durationMs: Date.now() - startedAt, steps: stepResults, expected: expectedResults,
      findings: c.findings, notes: c.notes, consoleErrors: c.consoleErrors, pageErrors: c.pageErrors,
      nonGetRequests: c.nonGet, safetyViolations, viewport: page.viewportSize(), finalUrl: page.url(), mainStatus: c.mainStatus,
    };
    await page.screenshot({ path: testInfo.outputPath('final.png') }).catch(() => {});
    await testInfo.attach('tc_result.json', { body: JSON.stringify(result, null, 2), contentType: 'application/json' });
    await testInfo.attach('requests.json', { body: JSON.stringify(c.nonGet, null, 2), contentType: 'application/json' });
    await page.waitForTimeout(800).catch(() => {});

    if (status === 'safety_violation') throw new Error(`SAFETY VIOLATION: ${[...safetyViolations, ...submitted2xx.map((x) => x.url)].join(' | ')}`);
    if (status === 'script_error') throw new Error(`SCRIPT_ERROR: ${(execFail as any).error || (execFail as any).actual}`);
    if (status === 'failed') throw new Error(`ASSERTION: ${failed.map((f) => `[${f.n}] ${f.text.slice(0, 80)} => ${f.actual}`).join(' || ')}`);
  });
}

// ---------------------------------------------------------------- overlays + caption
async function dismissOverlays(page: Page): Promise<string> {
  const sels = ['#hs-eu-decline-button', '#onetrust-accept-btn-handler', '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll', 'button:has-text("Accept All")', 'button:has-text("Accept all")', 'button:has-text("Accept")', 'button:has-text("Got it")', '[aria-label="Close"]:visible', '.cookie-close'];
  for (const s of sels) {
    const l = page.locator(s).first();
    if (await l.isVisible().catch(() => false)) {
      const txt = norm((await l.innerText().catch(() => '')) || s);
      const inCookie = /cookie|consent|onetrust|cybot|accept/i.test(s + ' ' + txt);
      if (!inCookie && s.includes('Close')) {
        // only close generic popups that overlay the page (not menus)
        const modal = await l.evaluate((e) => !!e.closest('[role=dialog],.modal,.popup,.hs-modal')).catch(() => false);
        if (!modal) continue;
      }
      await l.click({ timeout: 2000 }).catch(() => {});
      return `${s} (${txt.slice(0, 30)})`;
    }
  }
  return '';
}
export async function setCaption(page: Page, text: string) {
  await page.evaluate((t) => {
    let el = document.getElementById('__kawach_caption');
    if (!el) {
      el = document.createElement('div'); el.id = '__kawach_caption';
      el.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;background:rgba(15,23,42,.88);color:#fff;font:600 13px/1.3 system-ui,sans-serif;padding:6px 10px;pointer-events:none;white-space:normal;max-height:48px;overflow:hidden';
      document.documentElement.appendChild(el);
    }
    el.textContent = t;
  }, text).catch(() => {});
}

// ---------------------------------------------------------------- link checker (GET, manual redirects, retries on 502/503/504)
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';
export async function linkCheck(request: APIRequestContext, url: string, maxHops = 6): Promise<LinkResult> {
  let cur = url, hops = 0, status = 0, title = '', hasH1 = false, error: string | undefined;
  for (; hops <= maxHops; ) {
    let resp: any = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      await throttle('linkcheck', cur);
      try {
        resp = await request.get(cur, { maxRedirects: 0, timeout: 15000, failOnStatusCode: false, headers: { 'User-Agent': UA } });
        if ([502, 503, 504].includes(resp.status()) && attempt < 2) { continue; }
        break;
      } catch (e: any) { error = String(e.message || e).slice(0, 160); resp = null; if (attempt === 2) break; }
    }
    if (!resp) { status = 0; break; }
    status = resp.status();
    const loc = resp.headers()['location'];
    if (status >= 300 && status < 400 && loc) { cur = new URL(loc, cur).toString(); hops++; continue; }
    if (status < 400 && /html/i.test(resp.headers()['content-type'] || '')) {
      const body = await resp.text().catch(() => '');
      const m = body.match(/<title[^>]*>([\s\S]*?)<\/title>/i); title = norm(m ? m[1] : ''); hasH1 = /<h1[\s>]/i.test(body);
    }
    break;
  }
  const bad = status === 0 || status >= 400 || /\b404\b|not found/i.test(title);
  return { url, status, finalUrl: cur, hops, title, ok: !bad, hasH1, error };
}

export { expect };
