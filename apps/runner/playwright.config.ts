import { defineConfig, devices } from '@playwright/test';

// Specs live outside runner/ (in runs/<id>/scripts/ or hand-written/ or tests-smoke/).
// Scripts import only from runner/fixtures.ts (e.g. '../../../runner/fixtures' or '../fixtures'),
// which resolves @playwright/test directly within runner/node_modules without requiring
// external spec folders to have their own node_modules or dependencies.

const specDir = process.env.SPEC_DIR;
if (!specDir) {
  throw new Error('SPEC_DIR is not set');
}

export default defineConfig({
  testDir: specDir,
  testMatch: '**/*.spec.ts',
  outputDir: process.env.OUTPUT_DIR || './test-results',
  fullyParallel: true,
  workers: Number(process.env.WORKERS ?? 2),
  retries: 0,
  forbidOnly: true,
  timeout: Number(process.env.TEST_TIMEOUT_MS ?? 45000),
  expect: {
    timeout: 10000,
  },
  reporter: [
    ['json', { outputFile: process.env.JSON_REPORT || './pw-report.json' }],
    ['list'],
  ],
  use: {
    baseURL: process.env.BASE_URL,
    headless: process.env.HEADLESS === 'false' ? false : true,
    viewport: { width: 1366, height: 768 },
    locale: 'en-US',
    timezoneId: 'UTC',
    actionTimeout: 15000,
    navigationTimeout: 30000,
    trace: 'on',
    screenshot: 'on',
    video: {
      mode: 'on',
      size: { width: 1366, height: 768 },
    },
    launchOptions: {
      slowMo: Number(process.env.QA_VIDEO_SLOWMO || 0),
    },
    ignoreHTTPSErrors: process.env.IGNORE_HTTPS_ERRORS === 'true',
    userAgent:
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    extraHTTPHeaders: {
      'Accept-Language': 'en-US,en;q=0.9',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
      ...(process.env.X_QA_TOKEN ? { 'X-QA-Token': process.env.X_QA_TOKEN } : {}),
    },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
