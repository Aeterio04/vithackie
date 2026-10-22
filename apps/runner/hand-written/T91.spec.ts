import { test, expect } from '../fixtures';

test('T91: Deliberate assertion failure', async ({ page }) => {
  await page.goto('/login');
  await expect(page.locator('h1')).toHaveText('Nope');
});
