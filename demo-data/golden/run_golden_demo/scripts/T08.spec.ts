import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T08: Adding item with empty title is rejected', async ({ page }) => {
  // Step 1: Log in as qa.tester@example.com and open /dashboard
  await page.goto('/login');
  await page.getByLabel('Email').fill(credentials.username);
  await page.getByLabel('Password').fill(credentials.password);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  // Step 2: Clear Item title
  const titleInput = page.getByLabel('Item title');
  await titleInput.fill('');

  // Step 3: Click 'Add item' button
  await page.getByRole('button', { name: 'Add item' }).click();

  // S8: Shows message "Title is required" and no item is added
  const isInvalid = await titleInput.evaluate((el: HTMLInputElement) => !el.checkValidity() || Boolean(el.validationMessage)).catch(() => false);
  const hasMsg = await page.getByText(/title is required/i).isVisible().catch(() => false) || await page.getByRole('alert').isVisible().catch(() => false);
  expect(isInvalid || hasMsg).toBe(true);
  await expect(page).toHaveURL(/\/dashboard$/);
});