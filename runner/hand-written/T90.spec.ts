import { test, expect } from '../fixtures';

test('T90: Login page shows the Log in heading', async ({ page }) => {
  await page.goto('/login');
  await expect(page.locator('h1')).toHaveText('Log in');
});
