// qa_benchmark/deployed_sim/test_sim.mjs
// Automated verification suite for Deployed-Site Simulator using Playwright & qa_helpers

import { chromium } from '../../apps/runner/node_modules/@playwright/test/index.mjs';
import * as qaHelpers from '../../apps/runner/qa_helpers.ts';

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:4500';

async function runTests() {
  console.log(`Starting Deployed-Site Simulator Verification against ${BASE_URL}...`);
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  });
  const page = await context.newPage();

  let passed = 0;
  let total = 0;

  async function test(name, fn) {
    total++;
    try {
      process.stdout.write(`  [TEST] ${name} ... `);
      await fn();
      console.log('PASSED');
      passed++;
    } catch (err) {
      console.log(`FAILED: ${err.message}`);
    }
  }

  // Test 1: Consent Banner dismissal
  await test('Consent Banner auto-dismissal via dismissConsentOverlays', async () => {
    await page.goto(`${BASE_URL}/consent-banner`);
    await qaHelpers.waitForPageReady(page);

    const bannerBefore = await page.$('#consent-banner');
    if (!bannerBefore) throw new Error('Banner should be present before dismissal');

    const dismissed = await qaHelpers.dismissConsentOverlays(page);
    if (!dismissed) throw new Error('dismissConsentOverlays returned false');

    await page.click('#target-action');
    const resultText = await page.textContent('#action-result');
    if (!resultText.includes('Action executed successfully')) {
      throw new Error(`Expected action executed, got: ${resultText}`);
    }
  });

  // Test 2: Theme Toggle verification with expectThemeToggle and findControl
  await test('Theme Toggle detection via expectThemeToggle oracle', async () => {
    await page.goto(`${BASE_URL}/theme-test`);
    await qaHelpers.waitForPageReady(page);

    const toggleBtn = await qaHelpers.findControl(page, {
      name: /theme|dark|light|mode/i,
      role: 'button',
    });
    if (!toggleBtn) throw new Error('findControl failed to find icon-only theme toggle button');

    await qaHelpers.expectThemeToggle(page, {
      trigger: async () => {
        await toggleBtn.click();
      },
    });

    const currentTheme = await page.getAttribute('html', 'data-theme');
    // expectThemeToggle tests both initial toggle and revertibility, so final state is light
    if (currentTheme !== 'light') throw new Error(`Expected reverted light theme, got: ${currentTheme}`);
  });

  // Test 3: SPA Navigation and waitForPageReady
  await test('SPA dynamic view transition with waitForPageReady', async () => {
    await page.goto(`${BASE_URL}/spa#/home`);
    await qaHelpers.waitForPageReady(page);

    await page.click('#tab-dashboard');
    await qaHelpers.waitForPageReady(page);

    const title = await page.textContent('#view-title');
    if (!title.includes('Analytics Dashboard')) {
      throw new Error(`Expected Dashboard title, got: ${title}`);
    }
  });

  // Test 4: WAF Desktop UA vs X-QA-Token
  await test('WAF challenge allows desktop UA and X-QA-Token', async () => {
    // Standard desktop UA should pass
    const resp1 = await page.goto(`${BASE_URL}/waf-blocked`);
    if (resp1.status() !== 200) throw new Error(`Expected 200 for desktop UA, got ${resp1.status()}`);

    // With X-QA-Token header in context
    const tokenContext = await browser.newContext({
      extraHTTPHeaders: { 'X-QA-Token': 'test-qa-token-123' },
    });
    const tokenPage = await tokenContext.newPage();
    const resp2 = await tokenPage.goto(`${BASE_URL}/waf-blocked`);
    if (resp2.status() !== 200) throw new Error(`Expected 200 with X-QA-Token, got ${resp2.status()}`);
    const body2 = await tokenPage.content();
    if (!body2.includes('WAF Bypass Success')) throw new Error('Expected WAF Bypass message with token');
    await tokenContext.close();
  });

  await browser.close();
  console.log(`\nSimulator Verification: ${passed}/${total} tests passed.`);
  if (passed !== total) process.exit(1);
}

runTests().catch((err) => {
  console.error('Fatal test error:', err);
  process.exit(1);
});
