import { test, expect } from '../fixtures';

test('T92: Deliberate test error', async ({ page }) => {
  await page.goto('/login');
  // Clicking a non-existent button causes an actionTimeout/locator timeout (test error)
  await page.click('button:has-text("does-not-exist")', { timeout: 2000 });
});
