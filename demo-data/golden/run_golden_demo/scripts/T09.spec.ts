import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T09: Deleting an item removes only that item', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill(credentials.username);
  await page.getByLabel('Password').fill(credentials.password);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  const item1 = `${unique('item1')}`;
  const item2 = `${unique('item2')}`;

  await page.getByRole('button', { name: 'Add item' }).click();
  await page.getByLabel('Item title').fill(item1);
  await page.getByRole('button', { name: 'Add item' }).click();

  await page.getByRole('button', { name: 'Add item' }).click();
  await page.getByLabel('Item title').fill(item2);
  await page.getByRole('button', { name: 'Add item' }).click();

  await expect(page.getByText(item1)).toBeVisible();
  await expect(page.getByText(item2)).toBeVisible();

  const deleteButtons = page.getByRole('button', { name: 'Delete' });
  await deleteButtons.nth(1).click();

  // S9
  await expect(page.getByText(item2)).not.toBeVisible();
  await expect(page.getByText(item1)).toBeVisible();
});