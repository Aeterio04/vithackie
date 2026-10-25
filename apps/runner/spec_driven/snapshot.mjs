// Spec-driven explorer: visit ONLY the URLs the spec's test cases need, one DOM + ARIA snapshot per page.
// env: URLS_FILE (json array of urls), OUT_FILE, MAX_RPS (default 2), UA
import { chromium } from '@playwright/test';
import fs from 'node:fs';

const urls = JSON.parse(fs.readFileSync(process.env.URLS_FILE, 'utf-8'));
const gap = Math.ceil(1000 / Number(process.env.MAX_RPS || 2)) + 100;
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, userAgent: process.env.UA || undefined });
await ctx.addInitScript(() => {
  if (window !== window.top) return;
  const iv = setInterval(() => { const b = document.getElementById('hs-eu-decline-button'); if (b && b.offsetParent) b.click(); }, 300);
  setTimeout(() => clearInterval(iv), 30000);
});
const page = await ctx.newPage();
page.setDefaultTimeout(5000);
const out = [];
const t0 = Date.now();
for (const url of urls) {
  const started = Date.now();
  const rec = { url, ok: false };
  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    rec.status = resp ? resp.status() : 0;
    await page.locator('h1').first().waitFor({ state: 'visible', timeout: 6000 }).catch(() => {});
    rec.finalUrl = page.url();
    rec.title = await page.title();
    rec.data = await page.evaluate(() => {
      const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
      return {
        headings: [...document.querySelectorAll('h1,h2,h3')].slice(0, 40).map((h) => ({ level: Number(h.tagName[1]), text: h.innerText.replace(/\s+/g, ' ').trim().slice(0, 100) })),
        links: [...document.querySelectorAll('a[href]')].slice(0, 200).map((a) => ({ text: (a.innerText || a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 60), href: a.getAttribute('href') })),
        buttons: [...document.querySelectorAll('button,[role=button],.button,.w-button')].filter(vis).slice(0, 30).map((b) => ({ text: (b.innerText || b.getAttribute('aria-label') || '').trim().slice(0, 40) })),
        h1Visible: [...document.querySelectorAll('h1')].filter(vis).length,
        images: document.images.length,
        forms: document.querySelectorAll('form').length,
      };
    });
    rec.aria = await page.locator('body').ariaSnapshot({ timeout: 8000 }).then((s) => s.slice(0, 12000)).catch(() => '');
    rec.ok = true;
  } catch (e) { rec.error = String(e.message || e).slice(0, 200); }
  rec.ms = Date.now() - started;
  out.push(rec);
  const wait = gap - (Date.now() - started);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
}
fs.writeFileSync(process.env.OUT_FILE, JSON.stringify({ seconds: (Date.now() - t0) / 1000, pages: out }, null, 1));
await browser.close();
