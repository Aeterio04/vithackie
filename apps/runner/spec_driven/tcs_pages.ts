import {
  TcImpl, Ctx, BASE, heading, norm, looseRe, endsWithPath, pathOf, linksIn, visibleCount, imageState, throttle, scrollThrough,
  scrollTo, overflow, absUrl, dropdown, isFirstParty, isNoise, attr, mainText, clickSameTab,
} from './lib';
import type { Frame, Locator, Page } from '@playwright/test';

const home = async (c: Ctx) => { await c.goto('/'); };
const footerScope = (c: Ctx) => c.page.locator('footer');

// ------------------------------------------------------------------ generic page check
async function pageCheck(c: Ctx, p: string, opts: { demo?: boolean; textMin: number }) {
  const rec: any = { path: p };
  const errsBefore = c.consoleErrors.length + c.pageErrors.length;
  try {
    const r = await c.goto(p);
    rec.status = r ? r.status() : 0;
    rec.finalPath = pathOf(c.page.url());
    rec.h1 = await visibleCount(c.page.locator('h1'));
    rec.title = norm(await c.page.title());
    rec.text = (await mainText(c.page)).length;
    if (opts.demo) rec.demo = (await linksIn(c.page.locator('body'))).some((l) => endsWithPath(l.href, '/schedule-a-demo'));
    await scrollThrough(c.page, 150);
    rec.brokenImgs = await c.page.evaluate((base) => [...document.images].filter((i) => { const r = i.getBoundingClientRect(); let same = false; try { same = new URL(i.currentSrc || i.src).hostname.endsWith('imocha.io'); } catch {} return same && r.width > 0 && r.height > 0 && i.complete && i.naturalWidth === 0; }).map((i) => i.src), BASE);
    rec.errors = c.consoleErrors.length + c.pageErrors.length - errsBefore;
    rec.errorTexts = [...c.consoleErrors, ...c.pageErrors].slice(-3);
  } catch (e: any) { rec.error = String(e.message).slice(0, 200); }
  return rec;
}
const summarize = (recs: any[]) => recs.map((r) => `${r.path}:${r.error ? 'ERR' : `${r.status}/h1=${r.h1}/txt=${r.text}/err=${r.errors}`}`).join(' | ');

// ------------------------------------------------------------------ form helpers (works across frames)
interface FieldState { name: string; type: string; required: boolean; invalid: boolean; ariaInvalid: boolean; errText: string; value: string }
async function formFrames(page: Page): Promise<Frame[]> { return page.frames(); }
async function readFields(page: Page): Promise<{ fields: FieldState[]; errorTexts: string[]; frameUrls: string[] }> {
  const fields: FieldState[] = []; const errorTexts: string[] = []; const frameUrls: string[] = [];
  for (const f of await formFrames(page)) {
    const res = await f.evaluate(() => {
      const vis = (e: Element) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
      const out: any[] = [];
      document.querySelectorAll('input,select,textarea').forEach((el) => {
        const i = el as HTMLInputElement;
        if (['hidden', 'submit', 'button', 'image', 'reset'].includes(i.type) || !vis(i)) return;
        const label = (i.labels && i.labels[0]?.innerText) || i.getAttribute('aria-label') || i.placeholder || i.name || i.id;
        const wrap = i.closest('.hs-form-field, .field, .form-group, label, div') as HTMLElement | null;
        const errEl = wrap?.querySelector('.hs-error-msg, .hs-error-msgs, [class*=error], [role=alert]') as HTMLElement | null;
        out.push({
          name: (label || '').toString().replace(/\s+/g, ' ').trim().slice(0, 40), type: i.type || i.tagName.toLowerCase(),
          required: (i.required && !(i.tagName === 'SELECT' && i.value !== '') && !(i.type === 'checkbox' && !i.required)) || i.getAttribute('aria-required') === 'true' || (!!wrap?.querySelector('.hs-form-required') && i.value === '' && i.type !== 'checkbox'),
          invalid: !i.validity.valid, ariaInvalid: i.getAttribute('aria-invalid') === 'true' || /invalid|error/.test(i.className),
          errText: errEl && vis(errEl) ? errEl.innerText.trim().slice(0, 80) : '', value: i.value,
        });
      });
      const errs = [...document.querySelectorAll('.hs-error-msg, .hs-error-msgs label, [role=alert], .error-message, .w-form-fail')].filter(vis).map((e) => (e as HTMLElement).innerText.trim()).filter(Boolean);
      return { out, errs };
    }).catch(() => ({ out: [], errs: [] }));
    fields.push(...res.out); errorTexts.push(...res.errs); if (res.out.length) frameUrls.push(f.url().slice(0, 80));
  }
  return { fields, errorTexts, frameUrls };
}
const flagged = (f: FieldState) => f.invalid || f.ariaInvalid || !!f.errText;
async function clickSubmit(page: Page): Promise<boolean> {
  for (const f of await formFrames(page)) {
    const b = f.locator('input[type=submit], button[type=submit], button:has-text("Submit"), button:has-text("Book"), button:has-text("Get"), button:has-text("Send"), button:has-text("Request")').filter({ visible: true }).first();
    if (await b.count()) { await b.click({ timeout: 5000 }).catch(() => {}); await page.waitForTimeout(1200); return true; }
  }
  return false;
}
async function waitForFields(page: Page, ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { const r = await readFields(page); if (r.fields.length) return r; await page.waitForTimeout(500); }
  return readFields(page);
}
async function fillInvalid(page: Page): Promise<boolean> {
  let didEmail = false;
  for (const f of await formFrames(page)) {
    const email = f.locator('input[type=email], input[name*=email i], input[placeholder*=email i]').filter({ visible: true }).first();
    if (await email.count()) { await email.fill('not-an-email').catch(() => {}); didEmail = true; }
    const other = f.locator('input[type=text]:visible, input:not([type]):visible').first();
    if (await other.count()) await other.fill('a').catch(() => {});
  }
  return didEmail;
}

export const PAGE_TCS: Record<string, TcImpl> = {
  'TC-FOOT-001': {
    steps: [
      async (c) => { await c.goto('/'); await footerScope(c).last().scrollIntoViewIfNeeded().catch(() => {}); },
      async (c) => { c.st.links = await linksIn(footerScope(c)); c.st.text = norm(await footerScope(c).evaluateAll((fs) => fs.map((f) => (f as HTMLElement).innerText).join(' '))); },
    ],
    expected: [
      ['/skills-intelligence', '/products/skills-architecture', '/products/ai-skills-inference', '/work-intelligence', '/skills-taxonomy', '/pre-employment-testing/all-tests', '/products/skills-assessment'],
      ['/use-case/skill-gap-analysis', '/use-case/upskilling-and-reskilling', '/use-case/internal-mobility', '/use-case/strategic-workforce-planning', '/use-case/skills-based-hiring', '/ai-readiness'],
      ['/about-us', '/leadership-and-advisory-board', '/customers', '/contactus', '/careers', '/newsroom', '/events'],
      ['/blog', '/webinars', '/glossary', '/roi-through-skills-first-lens'],
    ].map((group): ((c: Ctx) => Promise<string>) => async (c) => {
      const miss = group.filter((g) => !c.st.links.some((l: any) => endsWithPath(l.href, g)));
      c.exp(!miss.length, `missing in footer: ${miss.join(', ')}`); return `${group.length} links present`;
    }).concat([
      async (c) => { const m = ['everest', 'idc-marketscape', 'brandon-hall'].filter((k) => !c.st.links.some((l: any) => l.href.toLowerCase().includes(k))); c.exp(!m.length, `missing recognition links: ${m}`); return '3 recognition links'; },
      async (c) => {
        const need: Array<[string, string]> = [['Workday', '/integrations/imocha-and-workday'], ['SAP SuccessFactors', '/integrations/imocha-and-sap-successfactors'], ['Lightcast', '/integrations/lightcast'], ['All Integration Partners', '/integration-partners']];
        const m = need.filter(([n, h]) => !c.st.links.some((l: any) => endsWithPath(l.href, h) && looseRe(n).test(l.text))).map(([n]) => n); c.exp(!m.length, `missing integration links: ${m}`); return '4 integration links';
      },
      async (c) => { const m = ['/security-guidelines', '/trust-center', '/privacy-policy', '/terms-of-service', '/security/gdpr', '/sitemap', '/ai-info'].filter((g) => !c.st.links.some((l: any) => endsWithPath(l.href, g))); c.exp(!m.length, `missing legal links: ${m}`); return '7 legal links'; },
      async (c) => { c.exp(/iMocha\.? All rights reserved/i.test(c.st.text), `footer text: ${c.st.text.slice(-200)}`); return 'copyright present'; },
    ]),
  },

  'TC-FOOT-002': {
    steps: [async (c) => { await c.goto('/'); await footerScope(c).last().scrollIntoViewIfNeeded().catch(() => {}); }, async (c) => {
      c.st.items = [];
      for (const n of ['SOC 2 Type II', 'ISO 27001:2022', 'GDPR']) {
        const t = footerScope(c).getByText(looseRe(n)).first();
        const visible = await t.isVisible().catch(() => false);
        const card = t.locator('xpath=ancestor::*[.//img][1]');
        const imgs = (await card.count()) ? await imageState(card, 3000) : [];
        const txt = (await card.count()) ? norm(await card.innerText()) : '';
        c.st.items.push({ n, visible, imgs, desc: txt.replace(looseRe(n), '').trim().length });
      }
    }],
    expected: [async (c) => { const bad = c.st.items.filter((x: any) => !x.visible || !x.imgs.length || x.imgs.some((i: any) => !i.loaded) || x.desc < 3); c.exp(!bad.length, bad.map((b: any) => `${b.n}: visible=${b.visible} imgs=${b.imgs.length} loaded=${b.imgs.every((i: any) => i.loaded)} desc=${b.desc}`).join('; ')); return '3 badges ok'; }],
  },

  'TC-FOOT-003': {
    steps: [async (c) => { await c.goto('/'); await footerScope(c).last().scrollIntoViewIfNeeded().catch(() => {}); }, async (c) => { c.st.links = await linksIn(footerScope(c)); }],
    expected: [
      async (c) => { const l = c.st.links.find((x: any) => /linkedin\.com/.test(x.href)); c.exp(!!l && new URL(l.href).hostname === 'www.linkedin.com' && new URL(l.href).pathname.startsWith('/company/imocha'), `linkedin=${l?.href}`); return l.href; },
      async (c) => { const l = c.st.links.find((x: any) => /youtube\.com/.test(x.href)); c.exp(!!l && new URL(l.href).hostname === 'www.youtube.com', `youtube=${l?.href}`); return l.href; },
      async (c) => { const soc = c.st.links.filter((x: any) => /linkedin|youtube|twitter|x\.com|facebook|instagram/.test(x.href)); const bad = soc.filter((x: any) => x.target === '_blank' && !/noopener/.test(x.rel)); c.exp(!bad.length, `new-tab links without noopener: ${bad.map((b: any) => b.href)}`); return `${soc.length} social links checked`; },
    ],
  },

  'TC-FOOT-004': {
    steps: [
      home,
      async (c) => {
        const all = await linksIn(footerScope(c)); const set = new Set<string>();
        for (const l of all) { try { const u = new URL(l.href, BASE + '/'); if (u.hostname === 'www.imocha.io') { u.hash = ''; set.add(u.toString()); } } catch {} }
        c.st.urls = [...set];
      },
      async (c) => { c.st.res = []; for (const u of c.st.urls) c.st.res.push(await c.linkCheck(u)); },
    ],
    expected: [async (c) => {
      const bad = c.st.res.filter((r: any) => !r.ok || r.hops > 3);
      c.exp(c.st.res.length > 0 && !bad.length, bad.map((b: any) => `${b.url} -> ${b.status} (hops ${b.hops}) "${b.title}" ${b.error || ''}`).join(' | ')); return `${c.st.res.length} footer links ok`;
    }],
  },

  'TC-LEGAL-001': {
    steps: ['/privacy-policy', '/terms-of-service', '/trust-center', '/security-guidelines'].map((p, i) => async (c: Ctx) => { (c.st.pages ||= []).push(await pageCheck(c, p, { textMin: 500 })); }),
    expected: [
      async (c) => { const bad = c.st.pages.filter((r: any) => r.error || !(r.status < 400) || !(r.h1 === 1 || r.title.length > 3) || r.text <= 500); c.exp(!bad.length, summarize(c.st.pages)); return summarize(c.st.pages); },
      async (c) => { const bad = c.st.pages.filter((r: any) => r.errors > 0); c.exp(!bad.length, `first-party errors on: ${bad.map((b: any) => b.path)}`); return 'no first-party errors'; },
    ],
  },

  'TC-FORM-001': {
    steps: [
      async (c) => { await c.goto('/schedule-a-demo'); const r = await waitForFields(c.page); c.st.initial = r; },
      async (c) => { const r = await readFields(c.page); c.st.list = r; c.notes.push('fields: ' + r.fields.map((f) => `${f.name}[${f.type}${f.required ? ',req' : ''}]`).join('; ')); },
      async (c) => { c.st.url0 = c.page.url(); c.st.submitted1 = await clickSubmit(c.page); c.st.after1 = await readFields(c.page); c.st.url1 = c.page.url(); },
      async (c) => { c.st.email = await fillInvalid(c.page); c.st.submitted2 = await clickSubmit(c.page); c.st.after2 = await readFields(c.page); },
    ],
    expected: [
      async (c) => { c.exp(c.st.list.fields.length >= 3, `visible fields=${c.st.list.fields.length} frames=${c.st.list.frameUrls}`); return `${c.st.list.fields.length} fields`; },
      async (c) => {
        const req = c.st.after1.fields.filter((f: FieldState) => f.required);
        if (!c.st.submitted1) { c.finding({ severity: 'info', title: 'Demo form submit control not reachable', detail: 'Validation part recorded as informational per TC.' }); return 'submit not reachable; informational'; }
        const unflagged = req.filter((f: FieldState) => !flagged(f));
        c.exp(req.length > 0 && !unflagged.length && !/thank/i.test(c.page.url()) && c.st.url1 === c.st.url0, `required=${req.length} without feedback: ${unflagged.map((f: FieldState) => f.name)} errorTexts=${c.st.after1.errorTexts.slice(0, 3)}`); return `${req.length} required fields flagged`;
      },
      async (c) => { if (!c.st.submitted2) return 'submit not reachable; informational'; const e = c.st.after2.fields.find((f: FieldState) => /mail/i.test(f.type + f.name)); c.exp(!!e && flagged(e), `email field: ${JSON.stringify(e)}`); return 'email flagged'; },
      async (c) => { const sent = c.nonGet.filter((x) => !x.blocked && x.status !== undefined && x.status < 300 && (isFirstParty(x.url) || /hsforms|submit/i.test(x.url))); const blocked = c.nonGet.filter((x) => x.blocked); c.exp(!sent.length, `lead-creating requests: ${sent.map((s) => s.url)}`); return `0 submissions sent; ${blocked.length} blocked by read-only guard; ${c.nonGet.length} non-GET total`; },
    ],
  },

  'TC-FORM-002': {
    steps: [
      async (c) => { await c.goto('/contactus'); c.st.initial = await waitForFields(c.page); },
      async (c) => { c.st.h1 = await visibleCount(c.page.locator('h1')); c.st.fields = await readFields(c.page); const body = norm(await c.page.locator('body').innerText()); c.st.contact = (await c.page.locator('a[href^="mailto:"], a[href^="tel:"]').count()) > 0 || /\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b|@imocha|address|street|suite|floor/i.test(body); },
      async (c) => { c.st.url0 = c.page.url(); c.st.s1 = await clickSubmit(c.page); c.st.after1 = await readFields(c.page); },
      async (c) => { c.st.email = await fillInvalid(c.page); c.st.s2 = await clickSubmit(c.page); c.st.after2 = await readFields(c.page); },
    ],
    expected: [
      async (c) => { c.exp(c.st.h1 === 1, `visible h1=${c.st.h1}`); return 'one h1'; },
      async (c) => { c.exp(c.st.contact, 'no visible email/phone/address detail'); return 'contact detail present'; },
      async (c) => { c.exp(c.st.s1 && c.st.after1.fields.some(flagged) && !/thank/i.test(c.page.url()), `submitReached=${c.st.s1} fields=${c.st.after1.fields.length} flagged=${c.st.after1.fields.filter(flagged).length} errs=${c.st.after1.errorTexts.slice(0, 3)}`); return 'validation feedback shown'; },
      async (c) => { const e = c.st.after2.fields.find((f: FieldState) => /mail/i.test(f.type + f.name)); c.exp(c.st.s2 && !!e && flagged(e), `email field: ${JSON.stringify(e)} submitReached=${c.st.s2}`); return 'email flagged'; },
    ],
  },

  'TC-PAGE-001': {
    steps: [async (c) => { c.st.recs = []; for (const p of ['/skills-intelligence', '/products/skills-architecture', '/products/ai-skills-inference', '/products/skills-assessment', '/work-intelligence', '/skills-taxonomy']) c.st.recs.push(await pageCheck(c, p, { demo: true, textMin: 500 })); }],
    expected: [
      async (c) => { const b = c.st.recs.filter((r: any) => r.error || !(r.status < 400)); c.exp(!b.length, summarize(b)); return summarize(c.st.recs); },
      async (c) => { const b = c.st.recs.filter((r: any) => r.h1 !== 1); c.exp(!b.length, `h1 counts: ${b.map((x: any) => `${x.path}=${x.h1}`)}`); return 'one h1 each'; },
      async (c) => { const b = c.st.recs.filter((r: any) => !r.demo); c.exp(!b.length, `no /schedule-a-demo link on: ${b.map((x: any) => x.path)}`); return 'demo CTA on each'; },
      async (c) => { const b = c.st.recs.filter((r: any) => r.errors > 0); c.exp(!b.length, `first-party errors: ${b.map((x: any) => `${x.path}=${x.errors} ${JSON.stringify(x.errorTexts)}`)}`); return 'no errors'; },
      async (c) => { const b = c.st.recs.filter((r: any) => !(r.text > 500)); c.exp(!b.length, `short text: ${b.map((x: any) => `${x.path}=${x.text}`)}`); return 'text > 500'; },
      async (c) => { const b = c.st.recs.filter((r: any) => r.brokenImgs?.length); c.exp(!b.length, b.map((x: any) => `${x.path}: ${x.brokenImgs.slice(0, 3)}`).join(' | ')); return 'no broken images'; },
    ],
  },

  'TC-PAGE-002': {
    steps: [async (c) => { c.st.recs = []; for (const p of ['/use-case/skill-gap-analysis', '/use-case/upskilling-and-reskilling', '/use-case/internal-mobility', '/use-case/strategic-workforce-planning', '/use-case/skills-based-hiring', '/ai-readiness']) c.st.recs.push(await pageCheck(c, p, { demo: true, textMin: 500 })); }],
    expected: [async (c) => {
      const bad = c.st.recs.filter((r: any) => r.error || !(r.status < 400) || r.h1 !== 1 || !r.demo || r.errors > 0 || !(r.text > 500) || r.brokenImgs?.length);
      const swp = c.st.recs.find((r: any) => r.path === '/use-case/strategic-workforce-planning');
      if (swp && swp.status >= 400) c.finding({ severity: 'high', title: 'Strategic Workforce Planning page returns an error', detail: `status ${swp.status}; the main navigation links to it` });
      c.exp(!bad.length, bad.map((r: any) => `${r.path}: status=${r.status} h1=${r.h1} demo=${r.demo} err=${r.errors} text=${r.text} broken=${r.brokenImgs?.length} ${r.error || ''}`).join(' | ')); return summarize(c.st.recs);
    }],
  },

  'TC-PAGE-003': {
    steps: [
      async (c) => { await c.goto('/pre-employment-testing/all-tests'); },
      async (c) => {
        c.st.search = c.page.locator('input[type=search], input[placeholder*=Search i]').filter({ visible: true }).first();
        c.st.items = c.page.locator('.w-dyn-item:visible').filter({ hasText: /Candidates Assessed/i });
        c.st.initial = await c.st.items.count();
        c.st.initialText = norm(await c.page.locator('body').innerText());
      },
      async (c) => {
        c.st.hasSearch = (await c.st.search.count()) > 0;
        if (c.st.hasSearch) { await c.st.search.fill('Python'); await c.page.waitForTimeout(3000); c.st.filtered = await c.st.items.count(); c.st.filteredTexts = await c.st.items.allInnerTexts(); c.st.noResults = /no results|no items|nothing found/i.test(await c.page.locator('body').innerText()); }
      },
      async (c) => { if (c.st.hasSearch) { await c.st.search.fill(''); await c.page.waitForTimeout(2500); c.st.cleared = await c.st.items.count(); } },
    ],
    expected: [
      async (c) => { c.exp(c.st.initial >= 10, `listed items=${c.st.initial}`); return `${c.st.initial} items`; },
      async (c) => {
        if (!c.st.hasSearch) { c.finding({ severity: 'info', title: 'No search control found', detail: 'Verified only the list' }); return 'no search control; list verified only'; }
        const mention = c.st.filteredTexts.filter((t: string) => /python/i.test(t)).length;
        c.exp((c.st.filtered !== c.st.initial) && (c.st.noResults || (c.st.filtered > 0 && mention === c.st.filtered) || c.st.filtered === 0), `initial=${c.st.initial} filtered=${c.st.filtered} mentionPython=${mention}`); return `filtered ${c.st.initial} -> ${c.st.filtered}`;
      },
      async (c) => { if (!c.st.hasSearch) return 'n/a'; c.exp(c.st.cleared > c.st.filtered, `after clear=${c.st.cleared}, filtered=${c.st.filtered}`); return `restored to ${c.st.cleared}`; },
    ],
  },

  'TC-PAGE-004': {
    steps: [
      async (c) => { await c.goto('/blog'); },
      async (c) => {
        const links = await linksIn(c.page.locator('main, body').first());
        const m = new Map<string, any>();
        for (const l of links) { const p = pathOf(l.href); if (/^\/blog\/[^/]+$/.test(p) && !m.has(p)) m.set(p, l); }
        c.st.cards = [...m.values()];
        const imgs = await imageState(c.page.locator('body'), 2500); c.st.imgBad = imgs.filter((i) => !i.loaded).length; c.st.imgN = imgs.length;
      },
      async (c) => {
        const first = c.st.cards[0]; const a = c.page.locator(`a[href="${first.href}"]`).first();
        const title = norm(first.text) || norm(await a.locator('xpath=ancestor::*[.//h2 or .//h3][1]').locator('h2,h3').first().innerText().catch(() => ''));
        c.st.cardTitle = title;
        await throttle('navigate', first.href);
        await Promise.all([c.page.waitForURL((u) => pathOf(u.toString()) === pathOf(first.href), { timeout: 20000 }), clickSameTab(a)]);
        await c.ready();
      },
      async (c) => { c.st.h1s = await c.page.locator('h1').evaluateAll((hs) => hs.filter((h) => h.getBoundingClientRect().width > 0).map((h) => (h as HTMLElement).innerText)); c.st.bodyLen = norm(await c.page.locator('body').innerText()).length; c.st.meta = /\b(20\d\d|min read|By\s+[A-Z])/i.test(norm(await c.page.locator('body').innerText())); },
    ],
    expected: [
      async (c) => { c.exp(c.st.cards.length >= 6 && c.st.imgBad === 0, `cards=${c.st.cards.length} images=${c.st.imgN} notLoaded=${c.st.imgBad}`); return `${c.st.cards.length} cards`; },
      async (c) => {
        const h = c.st.h1s.map(norm); const t = norm(c.st.cardTitle).toLowerCase();
        const match = h.length === 1 && (!t || h[0].toLowerCase().includes(t) || t.includes(h[0].toLowerCase()) || t.split(' ').slice(0, 4).every((w: string) => h[0].toLowerCase().includes(w)));
        c.exp(match && c.st.bodyLen > 500, `h1=${JSON.stringify(h)} cardTitle="${c.st.cardTitle}" bodyLen=${c.st.bodyLen} dateOrAuthor=${c.st.meta}`); return `h1="${h[0]}"`;
      },
    ],
  },

  'TC-PAGE-005': {
    steps: [
      async (c) => { await c.goto('/customers'); },
      async (c) => { const links = await linksIn(c.page.locator('body')); const m = new Map<string, any>(); for (const l of links) { if (/customer-stories\//.test(l.href) && !m.has(pathOf(l.href))) m.set(pathOf(l.href), l); } c.st.stories = [...m.values()]; c.st.logos = await c.page.locator('img').count(); },
      async (c) => {
        const first = c.st.stories[0]; const a = c.page.locator(`a[href="${first.href}"]`).first();
        await throttle('navigate', first.href);
        await Promise.all([c.page.waitForURL((u) => /customer-stories\//.test(u.toString()), { timeout: 20000 }), clickSameTab(a)]);
        await c.ready();
        c.st.h1 = await visibleCount(c.page.locator('h1')); c.st.len = norm(await c.page.locator('body').innerText()).length;
        await c.page.goBack({ waitUntil: 'domcontentloaded' }); await c.page.waitForTimeout(800); c.st.back = pathOf(c.page.url());
      },
    ],
    expected: [
      async (c) => { c.exp(c.st.stories.length >= 4 || c.st.logos >= 4, `stories=${c.st.stories.length} images=${c.st.logos}`); return `${c.st.stories.length} stories`; },
      async (c) => { c.exp(c.st.h1 === 1 && c.st.len > 500, `h1=${c.st.h1} len=${c.st.len}`); return 'story page ok'; },
      async (c) => { c.exp(c.st.back === '/customers', `back path=${c.st.back}`); return c.st.back; },
    ],
  },

  'TC-PAGE-006': {
    steps: [async (c) => { c.st.recs = []; for (const p of ['/events', '/webinars', '/careers', '/newsroom', '/about-us', '/leadership-and-advisory-board', '/integration-partners', '/resources', '/glossary']) c.st.recs.push(await pageCheck(c, p, { textMin: 300 })); }],
    expected: [async (c) => {
      const bad = c.st.recs.filter((r: any) => r.error || !(r.status < 400) || !(r.h1 === 1 || r.title.length > 3) || !(r.text > 300) || r.errors > 0);
      c.exp(!bad.length, bad.map((r: any) => `${r.path}: status=${r.status} h1=${r.h1} text=${r.text} err=${r.errors} ${JSON.stringify(r.errorTexts || [])} ${r.error || ''}`).join(' | ')); return summarize(c.st.recs);
    }],
  },

  'TC-LINK-001': {
    steps: [
      home,
      async (c) => {
        const all = await linksIn(c.page.locator('body')); const set = new Set<string>();
        for (const l of all) { if (!l.href || l.href.startsWith('#')) continue; try { const u = new URL(l.href, BASE + '/'); if (u.hostname === 'www.imocha.io') { u.hash = ''; set.add(u.toString()); } } catch {} }
        c.st.urls = [...set].slice(0, 80);
      },
      async (c) => { c.st.res = []; for (const u of c.st.urls) c.st.res.push(await c.linkCheck(u)); },
    ],
    expected: [
      async (c) => { const bad = c.st.res.filter((r: any) => r.status === 0 || r.status >= 400); c.exp(c.st.res.length > 0 && !bad.length, bad.map((b: any) => `${b.url} -> ${b.status} ${b.error || ''}`).join(' | ')); return `${c.st.res.length} links, all < 400`; },
      async (c) => { const bad = c.st.res.filter((r: any) => /\b404\b|not found/i.test(r.title)); c.exp(!bad.length, bad.map((b: any) => `${b.url} title="${b.title}"`).join(' | ')); return 'no error-page titles'; },
      async (c) => { const long = c.st.res.filter((r: any) => r.hops > 2); for (const l of long) c.finding({ severity: 'low', title: 'Redirect chain longer than 2 hops', detail: `${l.url} -> ${l.finalUrl} (${l.hops} hops)` }); return `${long.length} long redirect chains`; },
      async (c) => { c.notes.push('LINK TABLE ' + JSON.stringify(c.st.res.map((r: any) => [r.url.replace(BASE, ''), r.status, r.finalUrl.replace(BASE, '')]))); c.exp(c.st.res.length === c.st.urls.length, 'result rows != links'); return `${c.st.res.length} rows recorded`; },
    ],
  },

  'TC-RESP-001': {
    steps: [async (c) => {
      c.st.rows = [];
      for (const [w, h] of [[1440, 900], [1024, 768], [768, 1024], [390, 844]]) {
        await c.page.setViewportSize({ width: w, height: h });
        await c.goto('/');
        await scrollThrough(c.page, 300);
        await c.page.waitForTimeout(500);
        const o = await overflow(c.page);
        const m = await c.page.evaluate(() => {
          const vis = (e: Element | null) => { if (!e) return false; const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
          const h1 = document.querySelector('h1')!.getBoundingClientRect();
          const toggles = [...document.querySelectorAll('.w-dropdown-toggle')].filter((e) => vis(e) && /Products/i.test((e as HTMLElement).innerText));
          const burger = vis(document.querySelector('.w-nav-button'));
          const broken = [...document.images].filter((i) => vis(i) && i.complete && i.naturalWidth === 0).map((i) => i.currentSrc || i.src);
          return { h1l: h1.left, h1r: h1.right, desktop: toggles.length > 0, burger, broken };
        });
        c.st.rows.push({ w, sw: o.sw, iw: o.iw, ...m });
      }
    }],
    expected: [
      async (c) => { const b = c.st.rows.filter((r: any) => r.sw > r.iw + 1); c.exp(!b.length, c.st.rows.map((r: any) => `${r.w}: sw=${r.sw} iw=${r.iw}`).join(' | ')); return c.st.rows.map((r: any) => `${r.w}:${r.sw}/${r.iw}`).join(' '); },
      async (c) => { const b = c.st.rows.filter((r: any) => r.h1l < -1 || r.h1r > r.iw + 1); c.exp(!b.length, b.map((r: any) => `${r.w}: h1 ${r.h1l}..${r.h1r}`).join(' | ')); return 'h1 inside viewport'; },
      async (c) => { const b = c.st.rows.filter((r: any) => r.desktop === r.burger); c.exp(!b.length, c.st.rows.map((r: any) => `${r.w}: desktopMenu=${r.desktop} hamburger=${r.burger}`).join(' | ')); return 'exactly one nav mode per width'; },
      async (c) => { const b = c.st.rows.filter((r: any) => r.broken.length); c.exp(!b.length, b.map((r: any) => `${r.w}: ${r.broken.slice(0, 3)}`).join(' | ')); return 'no broken images'; },
    ],
  },

  'TC-SEO-001': {
    steps: [
      home,
      async (c) => {
        c.st.m = await c.page.evaluate(() => {
          const g = (s: string) => document.querySelector(s)?.getAttribute('content') || '';
          return { lang: document.documentElement.lang, viewport: g('meta[name=viewport]'), robots: g('meta[name=robots]'), ogTitle: g('meta[property="og:title"]'), ogDesc: g('meta[property="og:description"]'), ogImage: g('meta[property="og:image"]'), ogType: g('meta[property="og:type"]'), twitter: g('meta[name="twitter:card"]'), canonical: (document.querySelector('link[rel=canonical]') as HTMLLinkElement | null)?.href || '' };
        });
        if (c.st.m.ogImage) { await throttle('seo-image', c.st.m.ogImage); const r = await c.request.get(absUrl(c.st.m.ogImage), { timeout: 15000, failOnStatusCode: false }); c.st.img = { status: r.status(), type: r.headers()['content-type'] || '' }; }
      },
    ],
    expected: [
      async (c) => { c.exp(!!c.st.m.lang, 'html lang empty'); return `lang=${c.st.m.lang}`; },
      async (c) => { c.exp(/width=device-width/.test(c.st.m.viewport), `viewport="${c.st.m.viewport}"`); return c.st.m.viewport; },
      async (c) => { c.exp(!/noindex/i.test(c.st.m.robots), `robots="${c.st.m.robots}"`); return `robots="${c.st.m.robots}"`; },
      async (c) => { c.exp(!!(c.st.m.ogTitle && c.st.m.ogDesc && c.st.m.ogImage), `og:title="${c.st.m.ogTitle}" og:description len=${c.st.m.ogDesc.length} og:image="${c.st.m.ogImage}"`); return 'og tags present'; },
      async (c) => { c.exp(c.st.m.twitter === 'summary_large_image', `twitter:card="${c.st.m.twitter}"`); return c.st.m.twitter; },
      async (c) => { c.exp(!!c.st.img && c.st.img.status < 400 && /image/i.test(c.st.img.type), `og:image ${JSON.stringify(c.st.img)}`); return JSON.stringify(c.st.img); },
    ],
  },

  'TC-A11Y-001': {
    steps: [
      home,
      async (c) => { c.st.land = await c.page.evaluate(() => ({ header: document.querySelectorAll('header').length, nav: document.querySelectorAll('nav').length, main: document.querySelectorAll('main').length, footer: document.querySelectorAll('footer').length })); },
      async (c) => { await scrollThrough(c.page, 150); c.st.noAlt = await c.page.evaluate(() => [...document.images].filter((i) => !i.hasAttribute('alt')).filter((i) => { const r = i.getBoundingClientRect(); return r.width > 0; }).map((i) => i.currentSrc || i.src)); },
      async (c) => { c.st.alts = await c.page.evaluate(() => { const m: Record<string, Set<string>> = {}; const n: Record<string, number> = {}; Array.from(document.images).forEach((i) => { const a = (i.getAttribute('alt') || '').trim(); if (!a) return; n[a] = (n[a] || 0) + 1; (m[a] ||= new Set()).add(i.currentSrc || i.src); }); return Object.entries(n).filter(([, v]) => v > 3).map(([a, v]) => ({ alt: a, count: v, distinctSrc: m[a].size })); }); },
      async (c) => { c.st.unnamed = await c.page.evaluate(() => [...document.querySelectorAll('button, a[href]')].filter((e) => { const r = e.getBoundingClientRect(); if (r.width === 0 || r.height === 0) return false; const t = ((e as HTMLElement).innerText || '').trim() || e.getAttribute('aria-label') || e.getAttribute('title') || e.querySelector('img[alt]:not([alt=""])')?.getAttribute('alt') || e.getAttribute('aria-labelledby'); return !t; }).map((e) => e.outerHTML.slice(0, 100))); },
    ],
    expected: [
      async (c) => { const l = c.st.land; c.exp((l.header > 0 || l.nav > 0) && l.main > 0 && l.footer > 0, `landmarks ${JSON.stringify(l)}`); return JSON.stringify(l); },
      async (c) => { if (c.st.noAlt.length) c.finding({ severity: 'low', title: `${c.st.noAlt.length} visible image(s) without alt attribute`, detail: c.st.noAlt.slice(0, 8).join(', ') }); return `${c.st.noAlt.length} images without alt`; },
      async (c) => {
        const e = c.st.alts.find((a: any) => /ericsson logo/i.test(a.alt));
        if (e && e.distinctSrc > 1) c.finding({ severity: 'low', observation: 2, title: 'Alt text "Ericsson logo" reused for different logos', detail: `Known observation #2 CONFIRMED: used ${e.count} times for ${e.distinctSrc} distinct images.` });
        else c.notes.push('Known observation #2 REFUTED or not reproducible: ' + JSON.stringify(c.st.alts));
        for (const a of c.st.alts.filter((x: any) => x !== e && x.distinctSrc > 1)) c.finding({ severity: 'info', title: `Alt "${a.alt}" repeated ${a.count} times`, detail: `${a.distinctSrc} distinct images` });
        return `${c.st.alts.length} repeated alt texts`;
      },
      async (c) => { if (c.st.unnamed.length) c.finding({ severity: 'low', title: `${c.st.unnamed.length} control(s) without accessible name`, detail: c.st.unnamed.slice(0, 5).join(' || ') }); return `${c.st.unnamed.length} unnamed controls`; },
    ],
  },

  'TC-A11Y-002': {
    steps: [
      home,
      async (c) => {
        await c.page.mouse.click(5, 300).catch(() => {});
        await c.page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); window.getSelection()?.collapse(document.body, 0); });
        c.st.seq = [];
        for (let i = 0; i < 25; i++) {
          await c.page.keyboard.press('Tab'); await c.page.waitForTimeout(80);
          c.st.seq.push(await c.page.evaluate(() => {
            const e = document.activeElement as HTMLElement | null; if (!e || e === document.body) return null;
            const s = getComputedStyle(e); const r = e.getBoundingClientRect();
            const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0; const shadow = s.boxShadow !== 'none';
            return { name: (e.innerText || e.getAttribute('aria-label') || e.getAttribute('alt') || e.tagName).trim().slice(0, 30), x: Math.round(r.left), y: Math.round(r.top), inHeader: !!e.closest('header,nav'), focusVisible: outline || shadow || e.matches(':focus-visible') && s.outlineStyle !== 'none' };
          }));
        }
      },
      async (c) => {
        await c.goto('/'); await c.page.mouse.click(5, 300).catch(() => {});
        await c.page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); window.getSelection()?.collapse(document.body, 0); });
        let hit = false;
        for (let i = 0; i < 25 && !hit; i++) {
          await c.page.keyboard.press('Tab'); await c.page.waitForTimeout(60);
          hit = await c.page.evaluate(() => /Book a Demo/i.test((document.activeElement as HTMLElement | null)?.innerText || ''));
        }
        c.st.reached = hit;
        if (hit) { await throttle('navigate', 'bookdemo'); await Promise.all([c.page.waitForURL((u) => /schedule-a-demo/.test(u.toString()), { timeout: 15000 }).catch(() => {}), c.page.keyboard.press('Enter')]); await c.page.waitForTimeout(1500); }
        c.st.pathAfter = pathOf(c.page.url());
      },
    ],
    expected: [
      async (c) => {
        const hdr = c.st.seq.filter((s: any) => s && s.inHeader).slice(0, 12);
        const bad = hdr.filter((s: any, i: number) => i > 0 && s.x < hdr[i - 1].x - 8 && Math.abs(s.y - hdr[i - 1].y) < 40);
        c.exp(hdr.length >= 4 && !bad.length, `header focus order: ${hdr.map((s: any) => `${s.name}@${s.x}`).join(' > ')}`); return hdr.map((s: any) => s.name).join(' > ');
      },
      async (c) => { const f = c.st.seq.filter(Boolean); const ok = f.filter((s: any) => s.focusVisible).length; const pct = f.length ? Math.round((100 * ok) / f.length) : 0; c.exp(f.length > 0 && pct >= 90, `${ok}/${f.length} focused elements with visible indicator (${pct}%)`); return `${pct}% visible focus`; },
      async (c) => { c.exp(c.st.reached && c.st.pathAfter === '/schedule-a-demo', `reachedByTab=${c.st.reached} path=${c.st.pathAfter}`); return c.st.pathAfter; },
      async (c) => { const f = c.st.seq.filter(Boolean); c.exp(f.length >= 15 && new Set(f.map((s: any) => s.name + s.x + s.y)).size >= 10, `focus moved through ${new Set(f.map((s: any) => s.name + s.x)).size} distinct elements in 25 presses`); return 'not trapped'; },
    ],
  },

  'TC-PERF-001': {
    steps: [
      async (c) => {
        await throttle('navigate', '/');
        const t0 = Date.now();
        await c.page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 30000 });
        await c.page.locator('h1').first().waitFor({ state: 'visible', timeout: 20000 }).catch(() => {});
        c.st.h1Ms = Date.now() - t0;
      },
      async (c) => {
        await c.page.waitForTimeout(3000);
        c.st.perf = await c.page.evaluate(() => new Promise<any>((res) => {
          const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
          const reqs = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
          let lcp: number | null = null;
          try { new PerformanceObserver((l) => { const e = l.getEntries(); lcp = e[e.length - 1].startTime; }).observe({ type: 'largest-contentful-paint', buffered: true }); } catch {}
          setTimeout(() => res({ dcl: nav.domContentLoadedEventEnd, lcp, requests: reqs.length + 1, bytes: reqs.reduce((a, r) => a + (r.transferSize || 0), 0) }), 500);
        }));
      },
    ],
    expected: [
      async (c) => { c.exp(c.st.h1Ms <= 5000, `h1 visible after ${c.st.h1Ms} ms`); return `${c.st.h1Ms} ms`; },
      async (c) => { c.exp(c.st.perf.dcl <= 6000, `DOMContentLoaded ${Math.round(c.st.perf.dcl)} ms`); return `${Math.round(c.st.perf.dcl)} ms`; },
      async (c) => { c.exp(c.st.perf.lcp === null || c.st.perf.lcp <= 4000, `LCP ${Math.round(c.st.perf.lcp)} ms`); return `LCP ${c.st.perf.lcp === null ? 'n/a' : Math.round(c.st.perf.lcp) + ' ms'}`; },
      async (c) => { c.exp(c.st.perf.requests < 250, `${c.st.perf.requests} requests, ${Math.round(c.st.perf.bytes / 1024)} KB transferred`); return `${c.st.perf.requests} requests, ${Math.round(c.st.perf.bytes / 1024)} KB`; },
    ],
  },
};
