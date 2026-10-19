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
  workers: Number(process.env.WORKERS ?? 4),
  retries: 0,
  forbidOnly: true,
  timeout: Number(process.env.TEST_TIMEOUT_MS ?? 30000),
  expect: {
    timeout: 5000,
  },
  reporter: [
    ['json', { outputFile: process.env.JSON_REPORT || './pw-report.json' }],
    ['list'],
  ],
  use: {
    baseURL: process.env.BASE_URL,
    headless: true,
    viewport: { width: 1280, height: 720 },
    actionTimeout: 8000,
    navigationTimeout: 15000,
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'on',
    ignoreHTTPSErrors: false,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
