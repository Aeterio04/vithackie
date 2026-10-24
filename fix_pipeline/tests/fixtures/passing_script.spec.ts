import { test, expect } from '@playwright/test';

test('T00: Health check passing', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/App/);
});
