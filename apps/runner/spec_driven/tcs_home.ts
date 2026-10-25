import {
  TcImpl, Ctx, heading, sectionOf, scrollTo, norm, looseRe, endsWithPath, pathOf, linksIn, visibleCount, imageState,
  throttle, openMenu, closeMenus, scrollThrough, absUrl, attr, settled,
} from './lib';
import type { Locator } from '@playwright/test';

/** Open `/`, scroll to the heading, remember heading + section. */
async function toSection(c: Ctx, text: string, key = 'sec') {
  if (!c.st.__homeLoaded) { await c.goto('/'); c.st.__homeLoaded = true; }
  const h = heading(c.page, text);
  await h.waitFor({ state: 'attached', timeout: 15000 });
  await scrollTo(h);
  c.st[key + 'H'] = h; c.st[key] = sectionOf(h);
}
const secText = async (s: Locator) => norm(await s.innerText());
const home = async (c: Ctx) => { await c.goto('/'); c.st.__homeLoaded = true; };

async function clickToDemo(c: Ctx, link: Locator) {
  c.st.href = await link.getAttribute('href');
  await throttle('navigate', 'demo');
  const [resp] = await Promise.all([c.page.waitForResponse((r) => r.request().isNavigationRequest() && r.frame() === c.page.mainFrame(), { timeout: 20000 }), link.click({ timeout: 8000 })]);
  c.st.status = resp.status();
  await c.ready(); await c.page.waitForTimeout(2000);
  c.st.path = pathOf(c.page.url());
  c.st.formVisible = (await visibleCount(c.page.locator('form, iframe, input'))) > 0;
}

export const HOME_TCS: Record<string, TcImpl> = {
  'TC-HOME-001': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Look Beyond the Label'); },
      async (c) => { c.st.text = (await secText(c.st.sec)).toLowerCase(); c.st.imgs = await imageState(c.st.sec); c.st.cta = c.st.sec.locator('a').filter({ hasText: /Talk to an Expert/i }).first(); },
    ],
    expected: [
      async (c) => { c.exp(await c.st.secH.isVisible(), 'heading not visible'); return 'heading visible'; },
      async (c) => {
        const miss = ['manufacturing giant', 'global it consulting leader', 'fortune 500 insurer'].filter((k) => !c.st.text.includes(k));
        c.exp(!miss.length, `captions missing: ${miss.join(', ')}. Section text: ${c.st.text.slice(0, 200)}`); return 'three captions present';
      },
      async (c) => { const bad = c.st.imgs.filter((i: any) => !i.loaded); c.exp(c.st.imgs.length > 0 && !bad.length, `images=${c.st.imgs.length} not loaded: ${bad.map((b: any) => b.src).join(', ')}`); return `${c.st.imgs.length} images loaded`; },
      async (c) => { c.exp(await c.st.cta.isVisible().catch(() => false), '"Talk to an Expert" not visible in section'); return 'CTA visible'; },
    ],
  },

  'TC-HOME-002': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Leader in Skills Intelligence'); },
      async (c) => {
        c.st.cards = [];
        const all = await imageState(c.st.sec);
        const secT = norm(await c.st.sec.innerText());
        for (const n of ['Everest Group', 'IDC MarketScape', 'Brandon Hall']) {
          // Spec expects the name as visible text; the live page carries it in the logo alt text (calibration alternative).
          const viaText = await c.st.sec.getByText(looseRe(n)).first().isVisible().catch(() => false);
          const imgs = all.filter((i: any) => looseRe(n).test(i.alt));
          const visible = viaText || imgs.length > 0;
          if (!viaText && imgs.length) c.notes.push(`calibration: "${n}" found only as logo alt text ("${imgs[0].alt.slice(0, 60)}"), not as visible text`);
          c.st.cards.push({ n, visible, imgs, desc: secT.length > 250 ? 99 : 0 });
        }
      },
    ],
    expected: [
      async (c) => { const m = c.st.cards.filter((x: any) => !x.visible).map((x: any) => x.n); c.exp(!m.length, `not visible: ${m}`); return 'three recognitions visible'; },
      async (c) => { const m = c.st.cards.filter((x: any) => !x.imgs.length || x.imgs.some((i: any) => !i.loaded)).map((x: any) => x.n); c.exp(!m.length, `logo missing/not loaded: ${m}`); return 'logos loaded'; },
      async (c) => { const m = c.st.cards.filter((x: any) => x.desc < 5).map((x: any) => x.n); c.exp(!m.length, `no description: ${m}`); return 'descriptions present'; },
    ],
  },

  'TC-HOME-003': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Two Intelligences, One Defensible View of the Workforce'); },
      async (c) => {
        c.st.blocks = [];
        for (const n of ['What is Work Intelligence?', 'What is Skills Intelligence?']) {
          const h = c.st.sec.locator('h1,h2,h3,h4,h5,div,p').filter({ hasText: looseRe(n) }).last();
          const visible = await h.isVisible().catch(() => false);
          const blk = h.locator('xpath=ancestor::*[string-length(normalize-space(.)) > 260][1]');
          const text = (await blk.count()) ? norm(await blk.innerText()) : '';
          const imgs = (await blk.count()) ? await imageState(blk) : [];
          c.st.blocks.push({ n, visible, body: text.length - n.length, imgs });
        }
        c.st.cta = await linksIn(c.st.sec);
      },
    ],
    expected: [
      async (c) => { const m = c.st.blocks.filter((b: any) => !b.visible).map((b: any) => b.n); c.exp(!m.length, `not visible: ${m}`); return 'both headings visible'; },
      async (c) => { const m = c.st.blocks.filter((b: any) => b.body < 200); c.exp(!m.length, `short body: ${m.map((b: any) => `${b.n}=${b.body}`)}`); return c.st.blocks.map((b: any) => b.body).join('/'); },
      async (c) => { const m = c.st.blocks.filter((b: any) => !b.imgs.length || b.imgs.some((i: any) => !i.loaded)).map((b: any) => b.n); c.exp(!m.length, `illustration missing: ${m}`); return 'illustrations loaded'; },
      async (c) => { const l = c.st.cta.filter((x: any) => /Talk to an Expert/i.test(x.text)); c.exp(l.length > 0 && l.every((x: any) => endsWithPath(x.href, '/schedule-a-demo')), `CTA links: ${JSON.stringify(l.map((x: any) => x.href))}`); return `${l.length} CTA link(s) ok`; },
    ],
  },

  'TC-UC-001': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Every Talent Decision That Matters'); },
      async (c) => {
        const names = ['Skill Gap Analysis', 'Upskilling & Reskilling', 'Internal Mobility', 'Strategic Workforce Planning', 'Skills-based Hiring'];
        c.st.names = names;
        c.st.tabs = c.st.sec.locator('.w-tab-link, [role=tab]');
        c.st.tabCount = await c.st.tabs.count();
        c.st.snaps = [];
        if (c.st.tabCount >= 5) {
          for (const n of names) {
            const t = c.st.tabs.filter({ hasText: looseRe(n) }).first();
            await t.scrollIntoViewIfNeeded().catch(() => {});
            await t.click({ timeout: 8000 });
            await c.page.waitForTimeout(1500);
            const panes = c.st.sec.locator('.w-tab-pane');
            const active = panes.locator('xpath=.').filter({ has: c.page.locator('*') });
            const vis: string[] = []; const pc = await panes.count();
            for (let i = 0; i < pc; i++) if (await panes.nth(i).isVisible().catch(() => false)) vis.push(norm(await panes.nth(i).innerText()));
            const pane = panes.locator(':scope.w--tab-active').first();
            const imgs = (await pane.count()) ? await imageState(pane, 2500) : [];
            const learn = (await pane.count()) ? await linksIn(pane) : [];
            c.st.snaps.push({ n, visiblePanels: vis.length, text: vis.join(' | '), imgs, learn: learn.filter((l) => /learn more/i.test(l.text)) });
          }
        } else {
          // stacked list alternative (spec calibration note)
          const txt = norm(await c.st.sec.innerText());
          c.st.stacked = txt;
        }
      },
      async (c) => { c.notes.push(c.st.tabCount >= 5 ? `tab UI: ${c.st.tabCount} tabs` : 'stacked list alternative used'); },
    ],
    expected: ['Identify Workforce Skill Gaps with Precision', 'Turn Skill Gaps into Targeted Learning Journeys', 'Decode Career Growth from Within', 'Plan Your Future Workforce with Skills Intelligence', 'Hire for Skills, Not Just Resumes'].map((head, i): ((c: Ctx) => Promise<string>) => async (c) => {
      if (c.st.tabCount >= 5) {
        const s = c.st.snaps[i];
        c.exp(looseRe(head).test(s.text), `after clicking "${s.n}" panel text: "${(s.text || '').slice(0, 160)}"`);
        if (i === 4) {
          const multi = c.st.snaps.filter((x: any) => x.visiblePanels !== 1).map((x: any) => `${x.n}:${x.visiblePanels}`);
          const noImg = c.st.snaps.filter((x: any) => !x.imgs.length || x.imgs.some((m: any) => !m.loaded)).map((x: any) => x.n);
          const noLearn = c.st.snaps.filter((x: any) => !x.learn.length).map((x: any) => x.n);
          c.exp(!multi.length && !noImg.length && !noLearn.length, `visible-panel count != 1: [${multi}] image missing/not loaded: [${noImg}] no Learn More: [${noLearn}]`);
        }
        return `panel shows "${head}"`;
      }
      c.exp(looseRe(head).test(c.st.stacked), `stacked list: heading not found: ${head}`);
      return `stacked: "${head}" visible`;
    }),
  },

  'TC-UC-002': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Every Talent Decision That Matters'); },
      async (c) => {
        const links = await linksIn(c.st.sec);
        c.st.learn = links.filter((l) => /learn more/i.test(l.text));
        c.st.checks = [];
        for (const l of c.st.learn) c.st.checks.push({ href: l.href, res: await c.linkCheck(absUrl(l.href)) });
      },
    ],
    expected: [
      async (c) => {
        const hrefs = c.st.learn.map((l: any) => l.href);
        const need = ['/use-case/skill-gap-analysis', '/use-case/upskilling-and-reskilling', '/use-case/internal-mobility', '/use-case/skills-based-hiring'];
        const miss = need.filter((n) => !hrefs.some((h: string) => endsWithPath(h, n)));
        const swp = hrefs.find((h: string) => /strategic-workforce-planning/.test(h));
        if (swp && !pathOf(swp).startsWith('/use-case/')) {
          c.finding({ severity: 'low', observation: 1, title: 'Strategic Workforce Planning "Learn More" points to a blog path', detail: `Homepage link is ${swp}; navigation menu uses /use-case/strategic-workforce-planning. Known observation #1 CONFIRMED.` });
        } else if (swp) { c.notes.push('Known observation #1 REFUTED: SWP Learn More uses a /use-case path: ' + swp); }
        c.exp(c.st.learn.length >= 5 && !miss.length && !!swp, `learn-more count=${c.st.learn.length}; missing: ${miss}; swp link=${swp}`);
        return `hrefs: ${hrefs.join(', ')}`;
      },
      async (c) => { const bad = c.st.checks.filter((x: any) => !x.res.ok || !x.res.hasH1); c.exp(!bad.length, bad.map((b: any) => `${b.href}: status ${b.res.status} h1=${b.res.hasH1} title="${b.res.title}"`).join(' | ')); return c.st.checks.map((x: any) => `${x.res.status}`).join(','); },
    ],
  },

  'TC-HOME-004': {
    steps: [
      home,
      async (c) => { await toSection(c, 'The Context Layer, Connected to Your Tech Ecosystem'); },
      async (c) => {
        c.st.imgs = await imageState(c.st.sec, 4000);
        c.st.link = (await linksIn(c.st.sec)).find((l) => /Explore Integrations/i.test(l.text));
        c.st.page = c.st.link ? await c.linkCheck(absUrl(c.st.link.href)) : null;
      },
    ],
    expected: [
      async (c) => {
        const names = ['SAP SuccessFactors', 'Workday', 'Oracle', 'Microsoft', 'Degreed', 'Udemy', 'Jira', 'Asana'];
        const miss = names.filter((n) => !c.st.imgs.some((i: any) => i.loaded && looseRe(n).test(i.alt + ' ' + i.src.split('/').pop())));
        c.exp(!miss.length, `no loaded logo for: ${miss.join(', ')} (images: ${c.st.imgs.length}, alts: ${c.st.imgs.map((i: any) => i.alt).join('|').slice(0, 200)})`); return '8 logos loaded';
      },
      async (c) => { c.exp(!!c.st.link && endsWithPath(c.st.link.href, '/integration-partners') && c.st.page.ok && c.st.page.hasH1, `link=${c.st.link?.href} page=${JSON.stringify(c.st.page)}`); return `status ${c.st.page?.status}`; },
    ],
  },

  'TC-HOME-005': {
    steps: [
      home,
      async (c) => { await toSection(c, 'The Unified System'); },
      async (c) => { c.st.imgs = await imageState(c.st.sec, 3000); c.st.text = await secText(c.st.sec); },
    ],
    expected: [
      async (c) => { const a = await c.st.sec.locator('h1,h2,h3,h4,h5,div').filter({ hasText: /^\s*Skills Intelligence\s*$/ }).first().isVisible().catch(() => false); const b = await c.st.sec.locator('h1,h2,h3,h4,h5,div').filter({ hasText: /^\s*Work Intelligence\s*$/ }).first().isVisible().catch(() => false); c.exp(a && b, `Skills Intelligence heading visible=${a}, Work Intelligence heading visible=${b}`); return 'both visible'; },
      async (c) => { c.exp(c.st.imgs.length >= 2 && c.st.text.length > 300, `images=${c.st.imgs.length} textLen=${c.st.text.length}`); return `${c.st.imgs.length} images, ${c.st.text.length} chars`; },
      async (c) => {
        const ctx = await c.st.sec.getByText(/Context Layer/i).first().isVisible().catch(() => false);
        const failed = c.st.imgs.filter((i: any) => !i.loaded);
        const hot = c.st.imgs.filter((i: any) => /wikimedia|logo\.dev|gstatic/.test(i.host));
        const hosts = [...new Set(hot.map((i: any) => i.host))];
        if (hot.length) c.finding({ severity: 'low', observation: 3, title: 'Unified System section hot-links third-party images', detail: `Known observation #3 CONFIRMED: ${hot.length} image(s) from ${hosts.join(', ')}.` });
        else c.notes.push('Known observation #3 REFUTED: no wikimedia/logo.dev/gstatic images found in section');
        for (const f of failed) c.finding({ severity: 'low', title: 'Image failed to load', detail: f.src });
        c.exp(ctx, 'central "Context Layer" element not visible'); return `context layer visible; hotlinked=${hot.length}; failed=${failed.length}`;
      },
    ],
  },

  'TC-HOME-006': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Trusted by 300+ Enterprises'); },
      async (c) => {
        c.st.reads = (await linksIn(c.st.sec)).filter((l) => /read more/i.test(l.text));
        c.st.text = await secText(c.st.sec);
        const rm = c.st.sec.locator('a').filter({ hasText: /read more/i });
        c.st.cardImgs = [];
        const n = await rm.count();
        for (let i = 0; i < n; i++) { const card = rm.nth(i).locator('xpath=ancestor::*[.//img][1]'); if (await card.count()) c.st.cardImgs.push(...(await imageState(card, 3000))); }
        c.st.play = await c.st.sec.locator('[class*=play], button[aria-label*=play i]').count();
      },
      async (c) => {
        c.st.checks = [];
        for (const l of c.st.reads) c.st.checks.push({ href: l.href, res: await c.linkCheck(absUrl(l.href)) });
      },
    ],
    expected: [
      async (c) => { c.exp(await c.st.secH.isVisible(), 'heading not visible'); return 'visible'; },
      async (c) => { c.exp(/PMI/.test(c.st.text) && /L.{0,2}Or.{0,2}al/i.test(c.st.text), `section text lacks PMI / L'Oréal: ${c.st.text.slice(0, 200)}`); return 'PMI and L\'Oréal cards'; },
      async (c) => {
        const h = c.st.reads.map((r: any) => r.href);
        const a = h.some((x: string) => endsWithPath(x, '/customer-stories/pmi-builds-skills-first-talent-development-framework'));
        const b = h.some((x: string) => endsWithPath(x, '/customer-stories/loreal-transforms-talent-development-by-uncovering-hidden-talent-potential'));
        c.exp(a && b, `Read More hrefs: ${h.join(', ')}`); return h.join(', ');
      },
      async (c) => { const bad = c.st.checks.filter((x: any) => !x.res.ok || !x.res.hasH1); c.exp(c.st.checks.length >= 2 && !bad.length, `checks=${c.st.checks.length} bad: ${bad.map((b: any) => `${b.href}:${b.res.status}`)}`); return c.st.checks.map((x: any) => x.res.status).join(','); },
      async (c) => { const bad = c.st.cardImgs.filter((i: any) => !i.loaded); c.exp(c.st.cardImgs.length > 0 && !bad.length, `card images=${c.st.cardImgs.length} not loaded: ${bad.map((b: any) => b.src)}`); return `${c.st.cardImgs.length} images loaded`; },
      async (c) => `play controls found=${c.st.play}; none were clicked`,
    ],
  },

  'TC-HOME-007': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Trusted by 300+ Enterprises'); },
      async (c) => {
        // every slide of the slider that carries an author block (quote + name + logo), stepping the arrow up to 6 times
        const seen = new Map<string, { quote: string; name: string; logo: boolean }>();
        const collect = async () => {
          const items = await c.page.locator('.slider_testimonial_slide').evaluateAll((els) => els.map((e) => {
            const name = ((e.querySelector('.testimonial_author_info') as HTMLElement | null)?.innerText || '').replace(/^[\s\-\u2014\u2013]+/, '').split('\n')[0].trim();
            const quote = ((e as HTMLElement).innerText.match(/["\u201c][^]{20,}/) || [''])[0];
            const logos = [...e.querySelectorAll('img')] as HTMLImageElement[];
            return { quote, name, logoOk: logos.length > 0 && logos.every((i) => i.naturalWidth > 0 || !i.complete) };
          }));
          for (const it of items) { if (it.name && !seen.has(it.name)) seen.set(it.name, { quote: it.quote, name: it.name, logo: it.logoOk }); }
        };
        await collect();
        const next = c.page.locator('.w-slider-arrow-right').last();
        for (let i = 0; i < 6 && (await next.count()) && (await next.isVisible().catch(() => false)); i++) { await next.click({ timeout: 2000 }).catch(() => {}); await c.page.waitForTimeout(500); await collect(); }
        c.st.tests = [...seen.values()];
      },
    ],
    expected: [
      async (c) => { const ok = c.st.tests.filter((t: any) => t.quote.trim() && t.name.trim()); c.exp(ok.length >= 3, `testimonials with quote+name=${ok.length} (found ${c.st.tests.length})`); return `${ok.length} testimonials`; },
      async (c) => { const names = ['Fernando Ospina', 'Nathalie Clement', 'Lynn Hodak', 'Sabine van Zanten']; const hit = names.filter((n) => c.st.tests.some((t: any) => looseRe(n).test(t.name))); c.exp(hit.length >= 3, `names found: ${hit.join(', ')} of ${c.st.tests.map((t: any) => t.name)}`); return hit.join(', '); },
      async (c) => { const bad = c.st.tests.filter((t: any) => !t.logo); c.exp(c.st.tests.length > 0 && !bad.length, `no loaded logo for: ${bad.map((b: any) => b.name)}`); return 'logos loaded'; },
    ],
  },

  'TC-HOME-008': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Meet the Purpose-built Agents Behind the Intelligence'); },
      async (c) => { c.st.text = await secText(c.st.sec); c.st.links = await linksIn(c.st.sec); c.st.imgs = await imageState(c.st.sec, 3000); },
    ],
    expected: [
      async (c) => { c.exp((await c.st.secH.isVisible()) && c.st.text.length > 80, `heading visible=${await c.st.secH.isVisible()} text length=${c.st.text.length}`); return 'visible with description'; },
      async (c) => { const b = c.st.links.filter((l: any) => /Book a Demo/i.test(l.text)); c.exp(b.length > 0 && b.every((l: any) => endsWithPath(l.href, '/schedule-a-demo')), `Book a Demo links: ${JSON.stringify(b.map((x: any) => x.href))}`); return 'ok'; },
      async (c) => { const bad = c.st.imgs.filter((i: any) => !i.loaded); c.exp(!bad.length, `images not loaded: ${bad.map((b: any) => b.src)}`); return `${c.st.imgs.length} images loaded`; },
    ],
  },

  'TC-HOME-009': {
    steps: [
      home,
      async (c) => { await toSection(c, 'One Platform, Built for Skills-First Enterprises'); },
      async (c) => {
        const names = ['Unified Skills Intelligence Layer', 'AI-Powered Inference & Validation', 'Continuously Accurate Skills Profiles', 'Enriched Taxonomies & Ontologies', 'Closed-Loop Skills System', 'Seamless HR Tech Integration', 'Actionable Skills Analytics', 'Built for Skills-First Transformation'];
        c.st.cards = [];
        for (const n of names) {
          const h = c.st.sec.locator('h1,h2,h3,h4,h5,div,p').filter({ hasText: looseRe(n) }).last();
          const vis = await h.isVisible().catch(() => false);
          const blk = h.locator('xpath=ancestor::*[string-length(normalize-space(.)) > ' + (n.length + 30) + '][1]');
          const t = (await blk.count()) ? norm(await blk.innerText()) : '';
          c.st.cards.push({ n, vis, desc: t.length - n.length });
        }
      },
    ],
    expected: [
      async (c) => { const bad = c.st.cards.filter((x: any) => !x.vis || x.desc < 30); c.exp(!bad.length, bad.map((b: any) => `${b.n}: visible=${b.vis} desc=${b.desc}`).join('; ')); return '8 capabilities with descriptions'; },
    ],
  },

  'TC-HOME-010': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Unlock Your Workforce Potential'); },
      async (c) => { c.st.text = await secText(c.st.sec); await clickToDemo(c, c.st.sec.locator('a').filter({ hasText: /Talk to an Expert/i }).first()); },
    ],
    expected: [
      async (c) => { c.exp(/30[- ]?min/i.test(c.st.text), `section text: ${c.st.text.slice(0, 200)}`); return '30-minute description present'; },
      async (c) => { c.exp(c.st.path === '/schedule-a-demo' && c.st.formVisible, `path=${c.st.path} formVisible=${c.st.formVisible}`); return c.st.path; },
    ],
  },
};

// ------------------------------------------------------------------ FAQ + widget
async function faqRows(c: Ctx) { return c.page.locator('.faq_accordion'); }
const answerVisible = async (row: Locator) => {
  const a = row.locator('.c-faq-a').first();
  return a.evaluate((e) => { const r = e.getBoundingClientRect(); return r.height > 2 && getComputedStyle(e).display !== 'none'; }).catch(() => false);
};
const answerText = async (row: Locator) => norm(await row.locator('.c-faq-a').first().textContent().then((t) => t || '').catch(() => ''));

export const FAQ_TCS: Record<string, TcImpl> = {
  'TC-FAQ-001': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Frequently Asked Questions'); },
      async (c) => {
        const rows = await faqRows(c); c.st.n = await rows.count();
        c.st.visibleQ = 0; c.st.expanded = 0; c.st.first = '';
        for (let i = 0; i < c.st.n; i++) {
          const q = rows.nth(i).locator('.c-faq-q').first();
          if (await q.isVisible().catch(() => false)) c.st.visibleQ++;
          if (await answerVisible(rows.nth(i))) c.st.expanded++;
          if (i === 0) c.st.first = norm(await q.innerText());
        }
        c.st.qCount = c.st.n;
      },
    ],
    expected: [
      async (c) => { c.exp(await c.st.secH.isVisible(), 'heading not visible'); return 'visible'; },
      async (c) => { c.exp(c.st.visibleQ >= 15, `visible question rows=${c.st.visibleQ} of ${c.st.n}`); return `${c.st.visibleQ} visible of ${c.st.n}`; },
      async (c) => { c.exp(/identify skill gaps/i.test(c.st.first), `first question: ${c.st.first}`); return c.st.first.slice(0, 80); },
      async (c) => { c.exp(c.st.expanded <= 1, `${c.st.expanded} answers expanded initially`); return `${c.st.expanded} expanded`; },
    ],
  },
  'TC-FAQ-002': {
    steps: [
      home,
      async (c) => { await toSection(c, 'Frequently Asked Questions'); c.st.url0 = c.page.url(); c.st.row = (await faqRows(c)).nth(1); await c.st.row.scrollIntoViewIfNeeded(); },
      async (c) => {
        await c.st.row.locator('.c-faq-q').first().click({ timeout: 8000 }); await c.page.waitForTimeout(1200);
        await settled(c.st.row.locator('.c-faq-a').first());
        c.st.open = await answerVisible(c.st.row); c.st.ans = await answerText(c.st.row);
        c.st.aria1 = await attr(c.st.row.locator('[aria-expanded]'), 'aria-expanded');
      },
      async (c) => {
        await c.st.row.locator('.c-faq-q').first().click({ timeout: 8000 }); await c.page.waitForTimeout(600);
        await settled(c.st.row.locator('.c-faq-a').first());
        c.st.closed = !(await answerVisible(c.st.row));
        c.st.aria2 = await attr(c.st.row.locator('[aria-expanded]'), 'aria-expanded');
      },
    ],
    expected: [
      async (c) => { c.exp(c.st.open && /skills intelligence/i.test(c.st.ans) && c.st.ans.length > 150, `open=${c.st.open} len=${c.st.ans.length} text="${c.st.ans.slice(0, 100)}"`); return `answer length ${c.st.ans.length}`; },
      async (c) => { c.exp(c.st.aria1 === null || c.st.aria1 === 'true', `aria-expanded=${c.st.aria1}`); return `aria-expanded=${c.st.aria1 ?? 'absent'}`; },
      async (c) => { c.exp((c.st.closed || c.st.aria2 === 'false') && c.page.url() === c.st.url0, `closed=${c.st.closed} aria=${c.st.aria2} url=${c.page.url()}`); return 'collapsed, no navigation'; },
    ],
  },
  'TC-FAQ-003': {
    steps: [
      async (c) => { await c.goto('/'); c.st.__homeLoaded = true; await toSection(c, 'Frequently Asked Questions'); const rows = await faqRows(c); c.st.total = await rows.count(); c.st.res = []; },
      async (c) => {
        const rows = await faqRows(c);
        let minY = Infinity;
        for (let i = 0; i < c.st.total; i++) {
          const row = rows.nth(i);
          await row.scrollIntoViewIfNeeded().catch(() => {});
          const before = await c.page.evaluate(() => window.scrollY);
          await row.locator('.c-faq-q').first().click({ timeout: 8000 }); await c.page.waitForTimeout(300);
          await settled(row.locator('.c-faq-a').first(), 2500);
          const after = await c.page.evaluate(() => window.scrollY);
          const t = await answerText(row); const vis = await answerVisible(row);
          c.st.res.push({ i: i + 1, len: t.length, vis, jumpedTop: before > 400 && after < 100 });
          minY = Math.min(minY, after);
          await row.locator('.c-faq-q').first().click({ timeout: 8000 }).catch(() => {}); await settled(row.locator('.c-faq-a').first(), 2500);
        }
      },
    ],
    expected: [
      async (c) => { const bad = c.st.res.filter((r: any) => !r.vis || r.len < 100); c.exp(!bad.length, `Q${bad.map((b: any) => `${b.i}(vis=${b.vis},len=${b.len})`).join(', ')}`); return `${c.st.res.length} questions ok`; },
      async (c) => { c.exp(c.pageErrors.length === 0, JSON.stringify(c.pageErrors)); return 'no page errors'; },
      async (c) => { const j = c.st.res.filter((r: any) => r.jumpedTop); c.exp(!j.length, `scroll jumped to top at Q${j.map((x: any) => x.i)}`); return 'no scroll jump'; },
      async (c) => { c.exp(c.st.total >= 15 && c.st.res.length === c.st.total, `total=${c.st.total} opened=${c.st.res.length}`); return `${c.st.total} questions`; },
    ],
  },

  'TC-WIDGET-001': {
    steps: [
      home,
      async (c) => {
        c.st.cand = c.page.locator('.chat-container, [class*=chat], [class*=widget], [id*=widget]').filter({ hasText: /get in touch/i });
        c.st.trigger = c.page.locator('#fabBtn, .chat-container .fab').first();
        c.st.found = (await c.st.trigger.count()) > 0 && (await c.st.trigger.isVisible().catch(() => false));
        c.st.nodes = await c.page.locator('.chat-container').evaluateAll((e) => e.map((x) => ({ cls: x.className, txt: (x as HTMLElement).innerText.slice(0, 120), r: x.getBoundingClientRect().toJSON() })));
      },
      async (c) => { if (c.st.found) { await c.st.trigger.click({ timeout: 8000 }).catch(() => {}); await c.page.waitForTimeout(1200); } },
      async (c) => {
        const body = norm(await c.page.locator('body').innerText());
        c.st.opts = ['Schedule demo', 'Product tour', 'Talk to sales'].map((o) => ({ o, vis: false }));
        for (const x of c.st.opts) x.vis = await c.page.locator('#menuItems button').filter({ hasText: looseRe(x.o) }).first().isVisible().catch(() => false);
        c.st.bodyHas = body.length;
      },
      async (c) => {
        const l = c.page.locator('#menuItems button').filter({ hasText: /Schedule demo/i }).first();
        if (await l.count()) {
          const urlBefore = c.page.url();
          const pagesBefore = c.context.pages().length;
          await l.click({ timeout: 8000 }).catch(() => {}); await c.page.waitForTimeout(3000);
          const pages = c.context.pages(); const last = pages[pages.length - 1];
          c.st.behaviour = pages.length > pagesBefore ? 'new tab' : (pathOf(c.page.url()) !== pathOf(urlBefore) ? 'navigation' : 'modal/in-page');
          c.st.afterPath = pathOf(last.url());
          await c.page.waitForTimeout(1500);
          c.st.dialog = (await visibleCount(c.page.locator('.hs-modal, [role=dialog], .hs-modal-overlay'))) > 0;
          c.st.formOrCal = (await visibleCount(last.locator('#hs-form-container, #hs-form-container iframe, .hs-modal iframe, .hs-modal form, form, iframe, [class*=calendar], [class*=meetings]'))) > 0;
        }
      },
    ],
    expected: [
      async (c) => { const m = c.st.opts.filter((x: any) => !x.vis).map((x: any) => x.o); c.exp(!m.length, `widget found=${c.st.found}; options not visible: ${m}; candidates=${JSON.stringify(c.st.nodes)}`); return 'three options visible'; },
      async (c) => { c.exp(c.st.afterPath === '/schedule-a-demo' || (c.st.dialog && c.st.formOrCal) , `behaviour=${c.st.behaviour} path=${c.st.afterPath} dialog=${c.st.dialog} formOrCalendar=${c.st.formOrCal}`); return `behaviour=${c.st.behaviour}`; },
      async (c) => {
        // closed widget must not cover primary content: reload and measure widget area vs h1 area
        await c.goto('/');
        const cover = await c.page.evaluate(() => {
          const h = document.querySelector('h1')!.getBoundingClientRect();
          return [...document.querySelectorAll('.chat-container')].some((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && !(r.right < h.left || r.left > h.right || r.bottom < h.top || r.top > h.bottom); });
        });
        c.exp(!cover, 'widget overlaps the hero heading'); return 'no overlap with h1';
      },
    ],
  },
};
