import {
  TcImpl, Ctx, BASE, heading, norm, pathOf, endsWithPath, linksIn, visibleCount, notCovered, openMenu, closeMenus,
  panelLinks, dropdown, overflow, throttle, looseRe, attr,
} from './lib';
import type { Locator, Page } from '@playwright/test';

const hdrItem = (page: Page, name: string): Locator =>
  page.locator('header a, header .w-dropdown-toggle, nav a, nav .w-dropdown-toggle')
    .filter({ hasText: new RegExp('^\\s*' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*$', 'i') });

async function firstVisible(loc: Locator): Promise<Locator | null> {
  const n = await loc.count();
  for (let i = 0; i < n; i++) if (await loc.nth(i).isVisible().catch(() => false)) return loc.nth(i);
  return n ? loc.first() : null;
}

const home = async (c: Ctx) => { await c.goto('/'); };
const hrefsHave = (links: { href: string }[], suffixes: string[]) =>
  suffixes.filter((s) => !links.some((l) => endsWithPath(l.href, s)));
const namesHave = (links: { text: string }[], names: string[]) =>
  names.filter((n) => !links.some((l) => norm(l.text).toLowerCase().includes(n.toLowerCase())));

export const NAV_TCS: Record<string, TcImpl> = {
  'TC-LOAD-001': {
    steps: [
      async (c) => { const r = await c.goto('/', { noReady: true }); c.st.status = r ? r.status() : null; c.st.finalUrl = c.page.url(); },
      async (c) => { await c.ready(); },
      async (c) => {
        c.st.meta = await c.page.evaluate(() => ({
          title: document.title,
          desc: document.querySelector('meta[name=description]')?.getAttribute('content') || '',
          canonical: (document.querySelector('link[rel=canonical]') as HTMLLinkElement | null)?.href || '',
        }));
        c.st.h1 = await c.page.locator('h1').evaluateAll((hs) => hs.filter((h) => { const r = h.getBoundingClientRect(); return r.width > 0 && r.height > 0; }).map((h) => (h as HTMLElement).innerText));
      },
      async (c) => { await c.page.waitForTimeout(3000); },
    ],
    expected: [
      async (c) => { const host = new URL(c.st.finalUrl).hostname; c.exp(c.st.status === 200 && host === 'www.imocha.io', `status=${c.st.status} finalUrl=${c.st.finalUrl}`); return `status=${c.st.status} host=${host}`; },
      async (c) => { c.exp(/imocha/i.test(c.st.meta.title), `title="${c.st.meta.title}"`); return `title="${c.st.meta.title}"`; },
      async (c) => { c.exp(c.st.meta.desc.length > 50, `description length=${c.st.meta.desc.length}`); return `length=${c.st.meta.desc.length}`; },
      async (c) => { const canon = c.st.meta.canonical.replace(/\/+$/, ''); c.exp(canon === 'https://www.imocha.io', `canonical="${c.st.meta.canonical}"`); return c.st.meta.canonical; },
      async (c) => { c.exp(c.pageErrors.length === 0 && c.consoleErrors.length === 0, `pageErrors=${JSON.stringify(c.pageErrors)} firstPartyConsoleErrors=${JSON.stringify(c.consoleErrors)}`); return 'no errors'; },
      async (c) => { const h = c.st.h1 as string[]; c.exp(h.length === 1 && norm(h[0]).length > 10, `visible h1 count=${h.length} text=${JSON.stringify(h.map(norm))}`); return norm(h[0]); },
    ],
  },

  'TC-NAV-001': {
    steps: [
      home,
      async (c) => {
        const names = ['Products', 'Use Cases', 'Customers', 'Resources', 'Company', 'Login', 'Book a Demo'];
        c.st.items = {};
        for (const n of names) {
          const l = await firstVisible(hdrItem(c.page, n));
          c.st.items[n] = l ? { visible: await l.isVisible(), uncovered: await notCovered(l), href: await attr(l, 'href') } : null;
        }
        const logo = c.page.locator('header a:has(img[alt*="imocha" i]), nav a:has(img[alt*="imocha" i])').first();
        c.st.logo = await attr(logo, 'href');
      },
    ],
    expected: [
      async (c) => { const bad = Object.entries(c.st.items).filter(([, v]: any) => !v || !v.visible || !v.uncovered).map(([k]) => k); c.exp(!bad.length, `not visible/uncovered: ${bad.join(', ')}`); return 'all 7 visible and uncovered'; },
      async (c) => { c.exp(c.st.logo !== null && (c.st.logo === '/' || c.st.logo === 'https://www.imocha.io/'), `logo href=${c.st.logo}`); return `logo href=${c.st.logo}`; },
      async (c) => { c.exp(endsWithPath(c.st.items['Customers']?.href, '/customers'), `Customers href=${c.st.items['Customers']?.href}`); return c.st.items['Customers'].href; },
      async (c) => { const l = c.st.items['Login']?.href, b = c.st.items['Book a Demo']?.href; c.exp(l === 'https://app.imocha.io/' && endsWithPath(b, '/schedule-a-demo'), `Login=${l} BookADemo=${b}`); return `Login=${l} Book=${b}`; },
    ],
  },

  'TC-NAV-002': {
    steps: [
      async (c) => { await c.goto('/'); c.st.how = await openMenu(c.page, 'Products'); },
      async (c) => { await dropdown(c.page, 'Products').panel.waitFor({ state: 'visible', timeout: 2000 }); c.st.opened = true; },
      async (c) => { c.st.links = await panelLinks(c.page, 'Products'); },
      async (c) => { await closeMenus(c.page); c.st.stillOpen = await dropdown(c.page, 'Products').panel.isVisible().catch(() => false); },
    ],
    expected: [
      async (c) => {
        const miss = hrefsHave(c.st.links, ['/skills-intelligence', '/products/skills-architecture', '/products/ai-skills-inference', '/products/skills-assessment', '/work-intelligence', '/integrations/imocha-and-workday', '/integrations/imocha-and-sap-successfactors', '/integrations/lightcast', '/integration-partners']);
        c.exp(c.st.opened && !miss.length, `opened(${c.st.how})=${c.st.opened}, missing hrefs: ${miss.join(', ')}`); return `opened by ${c.st.how}; ${c.st.links.length} links`;
      },
      async (c) => { const miss = namesHave(c.st.links, ['Skills Intelligence', 'Skills Architecture', 'Skills Inference', 'Skills Assessment', 'Work Intelligence', 'Workday', 'SAP SuccessFactors', 'Lightcast']); c.exp(!miss.length, `missing names: ${miss.join(', ')}`); return 'all names present'; },
      async (c) => { c.exp(!c.st.stillOpen, 'panel still visible after Escape / pointer move'); return 'panel closed'; },
    ],
  },

  'TC-NAV-003': {
    steps: [home, async (c) => { c.st.how = await openMenu(c.page, 'Use Cases'); }, async (c) => { c.st.links = await panelLinks(c.page, 'Use Cases'); }],
    expected: [
      async (c) => {
        const missH = hrefsHave(c.st.links, ['/use-case/skill-gap-analysis', '/use-case/upskilling-and-reskilling', '/use-case/internal-mobility', '/use-case/strategic-workforce-planning', '/use-case/skills-based-hiring', '/ai-readiness']);
        const missN = namesHave(c.st.links.map((l: any) => ({ text: norm(l.text).replace(/&/g, '&') })), ['Skill Gap Analysis', 'Upskilling & Reskilling', 'Internal Mobility', 'Strategic Workforce Planning', 'Skills-based Hiring', 'AI-Readiness']);
        c.exp(!missH.length && !missN.length, `missing hrefs: [${missH}] missing names: [${missN}]`); return `opened by ${c.st.how}`;
      },
    ],
  },

  'TC-NAV-004': {
    steps: [
      home,
      async (c) => { await openMenu(c.page, 'Resources'); c.st.res = await panelLinks(c.page, 'Resources'); },
      async (c) => {
        await closeMenus(c.page); await openMenu(c.page, 'Company'); c.st.comp = await panelLinks(c.page, 'Company');
        c.st.openPanels = await visibleCount(c.page.locator('.w-dropdown-list'));
      },
    ],
    expected: [
      async (c) => { const m = hrefsHave(c.st.res, ['/pre-employment-testing/all-tests', '/blog', '/resources', '/webinars', '/events']); c.exp(!m.length, `Resources missing: ${m}`); return `${c.st.res.length} links`; },
      async (c) => { const m = hrefsHave(c.st.comp, ['/about-us', '/leadership-and-advisory-board', '/integration-partners', '/contactus', '/careers', '/newsroom']); c.exp(!m.length, `Company missing: ${m}`); return `${c.st.comp.length} links`; },
      async (c) => { c.exp(c.st.openPanels === 1, `visible menu panels=${c.st.openPanels}`); return 'one panel visible'; },
    ],
  },

  'TC-NAV-005': {
    steps: [
      async (c) => {
        const targets: Array<[string, string]> = [['Customers', '/customers'], ['About Us', '/about-us'], ['Contact Us', '/contactus'], ['Careers', '/careers'], ['Blogs', '/blog'], ['Skills Intelligence', '/skills-intelligence']];
        c.st.nav = [];
        for (const [name, target] of targets) {
          const rec: any = { name, target };
          try {
            await c.goto('/');
            let link: Locator | null = null;
            const find = async () => {
              const all = c.page.locator('header a[href], nav a[href]').filter({ hasText: looseRe(name) });
              const n = await all.count();
              for (let i = 0; i < n; i++) { const h = await all.nth(i).getAttribute('href'); if (h && pathOf(h) === target) return all.nth(i); }
              return null;
            };
            link = await find();
            if (link && !(await link.isVisible())) {
              for (const m of ['Products', 'Use Cases', 'Resources', 'Company']) {
                await closeMenus(c.page); await openMenu(c.page, m).catch(() => {});
                if (await link.isVisible().catch(() => false)) break;
              }
            }
            if (!link) throw new Error(`no nav link "${name}" -> ${target}`);
            await throttle('navigate', target);
            const [resp] = await Promise.all([
              c.page.waitForResponse((r) => r.request().isNavigationRequest() && r.frame() === c.page.mainFrame(), { timeout: 20000 }),
              link.click({ timeout: 8000 }),
            ]);
            await c.ready();
            rec.status = resp.status(); rec.path = pathOf(c.page.url());
            rec.h1 = await visibleCount(c.page.locator('h1'));
            await c.page.goBack({ waitUntil: 'domcontentloaded' });
            await c.page.waitForTimeout(500);
            rec.backPath = pathOf(c.page.url());
          } catch (e: any) { rec.error = String(e.message).slice(0, 200); }
          c.st.nav.push(rec);
        }
      },
    ],
    expected: [
      async (c) => {
        const bad = c.st.nav.filter((r: any) => r.error || r.path !== r.target || r.h1 !== 1 || !(r.status < 400) || r.backPath !== '/');
        const note = c.st.nav.map((r: any) => `${r.name}:${r.error ? 'ERR ' + r.error : `${r.path} s${r.status} h1=${r.h1} back=${r.backPath}`}`).join(' | ');
        c.exp(!bad.length, note); return note;
      },
    ],
  },

  'TC-NAV-006': {
    steps: [
      home,
      async (c) => {
        const l = await firstVisible(hdrItem(c.page, 'Login'));
        c.st.login = l ? { href: await l.getAttribute('href'), target: await l.getAttribute('target'), rel: await l.getAttribute('rel') } : null;
      },
      async (c) => { c.st.app = await c.linkCheck('https://app.imocha.io/'); },
    ],
    expected: [
      async (c) => { c.exp(c.st.login?.href === 'https://app.imocha.io/', `href=${c.st.login?.href}`); return c.st.login.href; },
      async (c) => { const t = c.st.login?.target, r = c.st.login?.rel || ''; c.exp(t !== '_blank' || /noopener/i.test(r), `target=${t} rel=${r}`); return `target=${t} rel=${r}`; },
      async (c) => { const a = c.st.app; c.exp(a.status > 0 && a.status < 400 && new URL(a.finalUrl).hostname === 'app.imocha.io', `status=${a.status} final=${a.finalUrl} ${a.error || ''}`); return `status=${a.status} final=${a.finalUrl}`; },
    ],
  },

  'TC-NAV-007': {
    steps: [
      home,
      async (c) => { c.st.banner = c.page.getByText(/Meet iMocha at/i).first(); await c.st.banner.waitFor({ state: 'visible', timeout: 8000 }); c.st.bannerText = norm(await c.st.banner.innerText()); },
      async (c) => {
        const l = c.page.getByRole('link', { name: /View Events/i }).first();
        await throttle('navigate', '/events');
        const [resp] = await Promise.all([c.page.waitForResponse((r) => r.request().isNavigationRequest() && r.frame() === c.page.mainFrame(), { timeout: 20000 }), l.click({ timeout: 8000 })]);
        await c.ready(); c.st.status = resp.status(); c.st.path = pathOf(c.page.url()); c.st.h1 = await visibleCount(c.page.locator('h1'));
      },
    ],
    expected: [
      async (c) => { c.exp(c.st.bannerText.length > 10, `banner="${c.st.bannerText}"`); return c.st.bannerText.slice(0, 80); },
      async (c) => { c.exp(c.st.path === '/events', `path=${c.st.path} status=${c.st.status}`); return c.st.path; },
      async (c) => { c.exp(c.st.h1 === 1, `visible h1=${c.st.h1}`); return 'one h1'; },
    ],
  },

  'TC-NAV-008': {
    steps: [
      async (c) => { await c.goto('/'); c.st.maxOverflow = 0; },
      async (c) => {
        const burger = c.page.locator('.w-nav-button').first();
        c.st.burgerVisible = await burger.isVisible();
        c.st.menuHiddenBefore = !(await c.page.locator('.w-nav-menu').first().isVisible().catch(() => false));
        c.st.productsHiddenBefore = !(await dropdown(c.page, 'Products').toggle.isVisible().catch(() => false));
        const o = await overflow(c.page); c.st.maxOverflow = Math.max(c.st.maxOverflow, o.sw - o.iw);
      },
      async (c) => { await c.page.locator('.w-nav-button').first().tap({ timeout: 8000 }).catch(async () => { await c.page.locator('.w-nav-button').first().click(); }); await c.page.waitForTimeout(700); },
      async (c) => {
        c.st.reach = {};
        for (const n of ['Products', 'Use Cases', 'Resources', 'Company', 'Login', 'Book a Demo']) {
          const l = await firstVisible(c.page.locator('a, .w-dropdown-toggle').filter({ hasText: new RegExp('^\\s*' + n + '\\s*$', 'i') }));
          if (l) { await l.scrollIntoViewIfNeeded().catch(() => {}); c.st.reach[n] = await l.isVisible(); } else c.st.reach[n] = false;
        }
        const dd = dropdown(c.page, 'Products').toggle;
        if (await dd.isVisible().catch(() => false)) { await dd.tap().catch(() => {}); await c.page.waitForTimeout(400); }
        const o = await overflow(c.page); c.st.maxOverflow = Math.max(c.st.maxOverflow, o.sw - o.iw);
      },
      async (c) => {
        await c.page.locator('.w-nav-button').first().tap({ timeout: 8000 }).catch(() => {}); await c.page.waitForTimeout(800);
        c.st.menuHiddenAfter = !(await c.page.locator('.w-nav-menu').first().isVisible().catch(() => false));
        c.st.scrollable = await c.page.evaluate(() => getComputedStyle(document.body).overflow !== 'hidden' && getComputedStyle(document.documentElement).overflow !== 'hidden');
        const o = await overflow(c.page); c.st.maxOverflow = Math.max(c.st.maxOverflow, o.sw - o.iw);
      },
    ],
    expected: [
      async (c) => { c.exp(c.st.burgerVisible && (c.st.menuHiddenBefore || c.st.productsHiddenBefore), `burger=${c.st.burgerVisible} menuHidden=${c.st.menuHiddenBefore} productsHidden=${c.st.productsHiddenBefore}`); return 'hamburger visible, desktop nav hidden'; },
      async (c) => { const m = Object.entries(c.st.reach).filter(([, v]) => !v).map(([k]) => k); c.exp(!m.length, `not reachable: ${m}`); return 'all six reachable'; },
      async (c) => { c.exp(c.st.menuHiddenAfter && c.st.scrollable, `menuHiddenAfter=${c.st.menuHiddenAfter} scrollable=${c.st.scrollable}`); return 'menu closed and page scrollable'; },
      async (c) => { c.exp(c.st.maxOverflow <= 1, `max horizontal overflow=${c.st.maxOverflow}px`); return `overflow=${c.st.maxOverflow}`; },
    ],
  },

  'TC-CTA-001': {
    steps: [
      home,
      async (c) => {
        const l = c.page.locator('a').filter({ hasText: /Talk to an Expert/i }).first();
        await l.scrollIntoViewIfNeeded().catch(() => {});
        c.st.href = await l.getAttribute('href');
        await throttle('navigate', 'cta');
        const [resp] = await Promise.all([c.page.waitForResponse((r) => r.request().isNavigationRequest() && r.frame() === c.page.mainFrame(), { timeout: 20000 }), l.click({ timeout: 8000 })]);
        c.st.status = resp.status();
      },
      async (c) => { await c.ready(); await c.page.waitForTimeout(2500); c.st.path = pathOf(c.page.url()); c.st.h1 = await visibleCount(c.page.locator('h1')); c.st.form = (await visibleCount(c.page.locator('form, iframe, input'))) > 0; },
    ],
    expected: [
      async (c) => { c.exp(c.st.path === '/schedule-a-demo', `path=${c.st.path}`); return c.st.path; },
      async (c) => { c.exp(c.st.h1 === 1, `visible h1=${c.st.h1}`); return 'one h1'; },
      async (c) => { c.exp(c.st.form, 'no visible form/iframe/input on the demo page'); return 'form element visible'; },
      async (c) => { c.exp(c.st.status < 400, `status=${c.st.status}`); return `status=${c.st.status}`; },
    ],
  },

  'TC-CTA-002': {
    steps: [
      home,
      async (c) => {
        c.st.ctas = (await linksIn(c.page.locator('body'))).filter((l) => /Talk to an Expert|Book a Demo|See How We Did it/i.test(l.text));
      },
      async (c) => { c.st.hrefs = c.st.ctas.map((l: any) => l.href); },
    ],
    expected: [
      async (c) => { c.exp(c.st.ctas.length >= 6, `found ${c.st.ctas.length} CTAs`); return `${c.st.ctas.length} CTAs`; },
      async (c) => {
        const bad = c.st.ctas.filter((l: any) => !l.href || l.href === '#' || !endsWithPath(l.href, '/schedule-a-demo'));
        c.exp(!bad.length, `wrong CTA targets: ${bad.map((b: any) => `"${b.text}"->${b.href}`).join('; ')}`); return 'all end with /schedule-a-demo';
      },
      async (c) => { const bad = c.st.ctas.filter((l: any) => !l.href || l.href === '#'); c.exp(!bad.length, `${bad.length} empty or # hrefs`); return 'none empty'; },
    ],
  },
};
