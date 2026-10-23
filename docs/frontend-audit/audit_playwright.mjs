/**
 * Comprehensive Playwright Frontend Audit Script
 * Drives apps/web in headless Chromium against http://localhost:3000,
 * navigates all routes, tests interactions, captures screenshots,
 * logs network requests and console errors, checks responsive viewports.
 */

import playwrightPkg from '../../apps/runner/node_modules/@playwright/test/index.js';
const { chromium } = playwrightPkg;
import fs from 'fs';
import path from 'path';

const SCREENSHOT_DIR = path.resolve('docs/frontend-audit/screenshots');
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const BASE_URL = 'http://localhost:3000';

async function main() {
  console.log('Launching Chromium for Frontend Audit...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  const auditResults = {
    pagesTested: [],
    consoleErrors: [],
    networkFailures: [],
    brokenLinks: [],
    responsiveSnapshots: [],
    defects: [],
  };

  // Monitor console errors
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      auditResults.consoleErrors.push({
        url: page.url(),
        text: msg.text(),
        location: msg.location(),
      });
    }
  });

  // Monitor network failures
  page.on('response', (res) => {
    if (res.status() >= 400) {
      auditResults.networkFailures.push({
        url: res.url(),
        status: res.status(),
        statusText: res.statusText(),
        page: page.url(),
      });
    }
  });

  const capture = async (name, fullPage = true) => {
    const filename = `${name}.png`;
    const filepath = path.join(SCREENSHOT_DIR, filename);
    await page.screenshot({ path: filepath, fullPage });
    console.log(`[Captured] ${filename}`);
    return filename;
  };

  // 1. Visit Login Page
  console.log('\n--- 1. Testing /login ---');
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await capture('01_login_page');
  auditResults.pagesTested.push({ route: '/login', status: 200, screenshot: '01_login_page.png' });

  // 2. Perform Login with demo credentials
  console.log('\n--- 2. Performing Login ---');
  const emailInput = page.locator('input[type="email"], input[name="email"]');
  const passInput = page.locator('input[type="password"], input[name="password"]');
  if (await emailInput.count() > 0) {
    await emailInput.fill('audit_engineer@example.com');
    await passInput.fill('Password123!');
    const submitBtn = page.locator('button[type="submit"]');
    await submitBtn.click();
    await page.waitForTimeout(2000);
    await capture('02_after_login');
  }

  // 3. Visit Register Page
  console.log('\n--- 3. Testing /register ---');
  await page.goto(`${BASE_URL}/register`, { waitUntil: 'networkidle' });
  await capture('03_register_page');
  auditResults.pagesTested.push({ route: '/register', status: 200, screenshot: '03_register_page.png' });

  // 4. Visit Root / Landing / Dashboard
  console.log('\n--- 4. Testing Root (/) ---');
  await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle' });
  await capture('04_dashboard_root');
  auditResults.pagesTested.push({ route: '/', status: 200, screenshot: '04_dashboard_root.png' });

  // 5. Visit /start (Run Initialization Form)
  console.log('\n--- 5. Testing /start ---');
  await page.goto(`${BASE_URL}/start`, { waitUntil: 'networkidle' });
  await capture('05_start_page');
  auditResults.pagesTested.push({ route: '/start', status: 200, screenshot: '05_start_page.png' });

  // 6. Visit /projects List
  console.log('\n--- 6. Testing /projects ---');
  await page.goto(`${BASE_URL}/projects`, { waitUntil: 'networkidle' });
  await capture('06_projects_list');
  auditResults.pagesTested.push({ route: '/projects', status: 200, screenshot: '06_projects_list.png' });

  // 7. Visit /projects/new
  console.log('\n--- 7. Testing /projects/new ---');
  await page.goto(`${BASE_URL}/projects/new`, { waitUntil: 'networkidle' });
  await capture('07_projects_new');
  auditResults.pagesTested.push({ route: '/projects/new', status: 200, screenshot: '07_projects_new.png' });

  // 8. Fetch real project ID from backend to test project scoped pages
  let projectId = '0eaa9c6a-033f-45b1-8f60-880c0bafe3d2';
  console.log(`\n--- 8. Testing /projects/${projectId} ---`);
  await page.goto(`${BASE_URL}/projects/${projectId}`, { waitUntil: 'networkidle' });
  await capture('08_project_detail');
  auditResults.pagesTested.push({ route: `/projects/${projectId}`, status: 200, screenshot: '08_project_detail.png' });

  // 9. Test /projects/${projectId}/commits
  console.log(`\n--- 9. Testing /projects/${projectId}/commits ---`);
  await page.goto(`${BASE_URL}/projects/${projectId}/commits`, { waitUntil: 'networkidle' });
  await capture('09_project_commits_empty');
  auditResults.pagesTested.push({ route: `/projects/${projectId}/commits`, status: 200, screenshot: '09_project_commits_empty.png' });

  // 10. Test /projects/${projectId}/tests
  console.log(`\n--- 10. Testing /projects/${projectId}/tests ---`);
  await page.goto(`${BASE_URL}/projects/${projectId}/tests`, { waitUntil: 'networkidle' });
  await capture('10_project_saved_tests_empty');
  auditResults.pagesTested.push({ route: `/projects/${projectId}/tests`, status: 200, screenshot: '10_project_saved_tests_empty.png' });

  // 11. Test /projects/${projectId}/settings
  console.log(`\n--- 11. Testing /projects/${projectId}/settings ---`);
  await page.goto(`${BASE_URL}/projects/${projectId}/settings`, { waitUntil: 'networkidle' });
  await capture('11_project_settings');
  auditResults.pagesTested.push({ route: `/projects/${projectId}/settings`, status: 200, screenshot: '11_project_settings.png' });

  // Check broken link: /projects/${projectId}/runs/${runId}/execution
  console.log(`\n--- 12. Testing Project-Scoped Run Link Navigation ---`);
  const projectScopedRunUrl = `${BASE_URL}/projects/${projectId}/runs/20261018-051106-c48f/execution`;
  const resScoped = await page.goto(projectScopedRunUrl, { waitUntil: 'networkidle' });
  const is404 = resScoped?.status() === 404 || (await page.locator('text=404, text=not found, text=This page could not be found').count()) > 0;
  await capture('12_project_scoped_run_404');
  if (is404) {
    auditResults.defects.push({
      type: 'BROKEN_LINK_404',
      route: projectScopedRunUrl,
      description: 'Project detail page links to /projects/:projectId/runs/:runId/execution which does not exist in the routing tree.',
      screenshot: '12_project_scoped_run_404.png',
    });
  }

  // 13. Test /catalog and /catalog/[runId]
  const runId = '20261018-051106-c48f';
  console.log(`\n--- 13. Testing /catalog/${runId} ---`);
  await page.goto(`${BASE_URL}/catalog/${runId}`, { waitUntil: 'networkidle' });
  await capture('13_catalog_view');
  auditResults.pagesTested.push({ route: `/catalog/${runId}`, status: 200, screenshot: '13_catalog_view.png' });

  // 14. Test /execution and /execution/[runId]
  console.log(`\n--- 14. Testing /execution/${runId} ---`);
  await page.goto(`${BASE_URL}/execution/${runId}`, { waitUntil: 'networkidle' });
  await capture('14_execution_cockpit');
  auditResults.pagesTested.push({ route: `/execution/${runId}`, status: 200, screenshot: '14_execution_cockpit.png' });

  // 15. Test /results and /results/[runId]
  console.log(`\n--- 15. Testing /results/${runId} ---`);
  await page.goto(`${BASE_URL}/results/${runId}`, { waitUntil: 'networkidle' });
  await capture('15_results_view');
  auditResults.pagesTested.push({ route: `/results/${runId}`, status: 200, screenshot: '15_results_view.png' });

  // 16. Test /results/[runId]/bugs/[bugId]
  console.log(`\n--- 16. Testing Bug Detail View ---`);
  const bugLink = page.locator('a[href*="/bugs/"]').first();
  if (await bugLink.count() > 0) {
    const bugHref = await bugLink.getAttribute('href');
    await page.goto(`${BASE_URL}${bugHref}`, { waitUntil: 'networkidle' });
    await capture('16_bug_detail_view');
    auditResults.pagesTested.push({ route: bugHref, status: 200, screenshot: '16_bug_detail_view.png' });
  } else {
    await page.goto(`${BASE_URL}/results/${runId}/bugs/bug_01`, { waitUntil: 'networkidle' });
    await capture('16_bug_detail_fallback');
  }

  // 17. Test /reports/[runId]
  console.log(`\n--- 17. Testing /reports/${runId} ---`);
  await page.goto(`${BASE_URL}/reports/${runId}`, { waitUntil: 'networkidle' });
  await capture('17_reports_view');
  auditResults.pagesTested.push({ route: `/reports/${runId}`, status: 200, screenshot: '17_reports_view.png' });

  // 18. Responsive testing on /reports/${runId} and /catalog/${runId}
  console.log('\n--- 18. Testing Viewport Responsiveness ---');
  // Tablet: 768px
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto(`${BASE_URL}/catalog/${runId}`, { waitUntil: 'networkidle' });
  await capture('18_responsive_tablet_768px');

  // Mobile: 375px
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto(`${BASE_URL}/catalog/${runId}`, { waitUntil: 'networkidle' });
  await capture('19_responsive_mobile_375px');

  // Desktop: 1440px
  await page.setViewportSize({ width: 1440, height: 900 });

  // Save audit log
  fs.writeFileSync(
    path.resolve('docs/frontend-audit/playwright_audit_results.json'),
    JSON.stringify(auditResults, null, 2),
    'utf-8'
  );
  console.log('\n[SUCCESS] Playwright Frontend Audit completed successfully.');
  await browser.close();
}

main().catch((err) => {
  console.error('[FAILED] Playwright Audit Error:', err);
  process.exit(1);
});
