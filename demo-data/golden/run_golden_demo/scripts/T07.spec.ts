import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T07: Adding item with non-empty title shows in list', async ({ page }) => {
  // Navigate to the application
  await page.goto('/');

  // Wait for the page to be ready
  await page.waitForLoadState('networkidle');

  // Find the input field for adding a new item
  const newItemInput = page.locator('input[placeholder*="item"], input[placeholder*="title"], input[type="text"]').first();
  
  // Type a non-empty title
  const itemTitle = `Test Item ${Date.now()}`;
  await newItemInput.fill(itemTitle);

  // Submit the form (click add button or press Enter)
  const addButton = page.locator('button:has-text("Add"), button[type="submit"]').first();
  if (await addButton.isVisible()) {
    await addButton.click();
  } else {
    await newItemInput.press('Enter');
  }

  // Wait for the item to appear in the list
  const listItem = page.locator(`li:has-text("${itemTitle}"), [data-testid*="item"]:has-text("${itemTitle}"), .item:has-text("${itemTitle}")`).first();
  await expect(listItem).toBeVisible({ timeout: 5000 });

  // Assert the item is in the list
  await expect(listItem).toContainText(itemTitle);
});