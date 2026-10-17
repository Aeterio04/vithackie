import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests-smoke',
  timeout: 30000,
  use: {
    headless: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
