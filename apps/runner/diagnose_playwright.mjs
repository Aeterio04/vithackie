// apps/runner/diagnose_playwright.mjs
// Companion Playwright probe runner for scripts/diagnose_target.py

import { chromium } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';

async function runProbe(profile, url, outDir) {
  const result = {
    profile,
    url,
    finalUrl: null,
    title: null,
    status: null,
    hasContent: false,
    textLength: 0,
    visibleElements: 0,
    consoleErrors: [],
    failedRequests: [],
    httpErrors: [],
    domContentLoadedMs: null,
    loadMs: null,
    networkIdleReached: false,
    networkIdleMs: null,
    screenshotPath: null,
    error: null,
  };

  const allowedHost = (() => {
    try {
      return new URL(url).hostname.toLowerCase();
    } catch {
      return '';
    }
  })();

  let browser = null;
  let context = null;

  try {
    const isHeaded = profile === 'headed';
    const isNewStandard = profile === 'new_standard' || profile === 'headed';

    const launchOptions = {
      headless: !isHeaded,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    };

    browser = await chromium.launch(launchOptions);

    const contextOptions = {
      viewport: isNewStandard ? { width: 1366, height: 768 } : { width: 1280, height: 720 },
      ignoreHTTPSErrors: !isNewStandard, // New standard validates TLS (ignoreHTTPSErrors: false)
      locale: 'en-US',
      timezoneId: 'UTC',
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    };

    if (isNewStandard) {
      contextOptions.extraHTTPHeaders = {
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
      };
    }

    context = await browser.newContext(contextOptions);
    const page = await context.newPage();

    // If profile === 'current', apply current platform's aggressive route blocking (only allowedHost)
    if (profile === 'current') {
      await page.route('**/*', (route) => {
        try {
          const reqHost = new URL(route.request().url()).hostname.toLowerCase();
          const proto = new URL(route.request().url()).protocol;
          if (proto === 'data:' || proto === 'blob:' || reqHost === allowedHost) {
            return route.continue();
          }
          return route.abort('blockedbyclient');
        } catch {
          return route.abort();
        }
      });
    }

    // Telemetry listeners
    const startTime = Date.now();
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        result.consoleErrors.push(msg.text().slice(0, 300));
      }
    });
    page.on('pageerror', (err) => {
      result.consoleErrors.push(String(err).slice(0, 300));
    });
    page.on('requestfailed', (req) => {
      const failure = req.failure()?.errorText || 'Unknown failure';
      result.failedRequests.push({
        url: req.url().slice(0, 200),
        failure,
      });
    });
    page.on('response', (res) => {
      if (res.status() >= 400) {
        try {
          const resHost = new URL(res.url()).hostname.toLowerCase();
          if (resHost === allowedHost) {
            result.httpErrors.push({
              url: res.url().slice(0, 200),
              status: res.status(),
              method: res.request().method(),
            });
          }
        } catch {}
      }
    });

    // Navigate with DOMContentLoaded
    const navStart = Date.now();
    let mainResp = null;
    try {
      mainResp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 25000 });
      result.domContentLoadedMs = Date.now() - navStart;
    } catch (e) {
      result.error = `Navigation error: ${e.message}`;
    }

    if (mainResp) {
      result.status = mainResp.status();
    }
    result.finalUrl = page.url();
    try {
      result.title = await page.title();
    } catch {}

    // Check load timing
    try {
      await page.waitForLoadState('load', { timeout: 10000 });
      result.loadMs = Date.now() - navStart;
    } catch {
      result.loadMs = null; // load didn't settle within 10s
    }

    // Check if networkidle is ever reached within 30s
    const idleCheckStart = Date.now();
    try {
      await page.waitForLoadState('networkidle', { timeout: 3000 }); // informational only; analytics keep sites busy
      result.networkIdleReached = true;
      result.networkIdleMs = Date.now() - idleCheckStart;
    } catch {
      result.networkIdleReached = false;
      result.networkIdleMs = null;
    }

    // Evaluate content in page
    try {
      const contentStats = await page.evaluate(() => {
        const text = (document.body?.innerText || '').trim();
        const visibleEls = Array.from(document.querySelectorAll('button, a, input, select, textarea, p, h1, h2, h3, h4, h5, h6, [role="button"]')).filter((el) => {
          const rect = el.getBoundingClientRect();
          const style = window.getComputedStyle(el);
          return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
        });
        return {
          textLength: text.length,
          visibleCount: visibleEls.length,
        };
      });
      result.textLength = contentStats.textLength;
      result.visibleElements = contentStats.visibleCount;
      result.hasContent = contentStats.textLength > 30 || contentStats.visibleCount > 2;
    } catch (evalErr) {
      result.error = (result.error ? result.error + '; ' : '') + `Eval error: ${evalErr.message}`;
    }

    // Save screenshot
    if (outDir) {
      try {
        fs.mkdirSync(outDir, { recursive: true });
        const shotPath = path.join(outDir, `screenshot_${profile}.png`);
        await page.screenshot({ path: shotPath, fullPage: false, timeout: 5000 });
        result.screenshotPath = shotPath;
      } catch (shotErr) {
        // Screenshot might fail on crashed page
      }
    }
  } catch (err) {
    result.error = err.message;
  } finally {
    if (context) await context.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
  }

  return result;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    console.error('Usage: node diagnose_playwright.mjs <url> [outDir]');
    process.exit(1);
  }
  const url = args[0];
  const outDir = args[1] || null;

  const results = {};

  // 1. Current Options
  results.current = await runProbe('current', url, outDir);

  // 2. New Standard Options
  results.new_standard = await runProbe('new_standard', url, outDir);

  // 3. Headed (skip if no display or test directly)
  try {
    results.headed = await runProbe('headed', url, outDir);
  } catch (e) {
    results.headed = { profile: 'headed', error: `Skipped (no display or headed error: ${e.message})` };
  }

  console.log('__PLAYWRIGHT_DIAG_OUTPUT_START__');
  console.log(JSON.stringify(results));
  console.log('__PLAYWRIGHT_DIAG_OUTPUT_END__');
}

main().catch((err) => {
  console.error('Fatal probe error:', err);
  process.exit(1);
});
