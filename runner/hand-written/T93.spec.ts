import { test, expect } from '../fixtures';

test('T93: Off-domain request is blocked', async ({ page }) => {
  await page.goto('/login');
  const result = await page.evaluate(async () => {
    try {
      await fetch('https://example.org/x');
      return 'not-blocked';
    } catch {
      return 'blocked';
    }
  });
  expect(result).toBe('blocked');
});
