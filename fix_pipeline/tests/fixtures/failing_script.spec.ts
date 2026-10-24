import { test, expect } from '@playwright/test';

test('T05: Counter increment test', async ({ page }) => {
  await page.goto('/counter');
  await page.click('button#add');
  await expect(page.locator('#count')).toHaveText('Count: 1');
});
