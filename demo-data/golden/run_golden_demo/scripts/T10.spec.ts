import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T10: Saving display name shows success and page has no errors', async ({ page }) => {
  const errors: string[] = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));

  await page.goto('/login');
  await page.getByLabel('Email').fill(credentials.username);
  await page.getByLabel('Password').fill(credentials.password);
  await page.getByRole('button', { name: 'Log in' }).click();

  await page.goto('/settings');
  await page.getByLabel('Display name').fill('Quality Tester');
  await page.getByRole('button', { name: 'Save settings' }).click();

  // S10
  await expect(page.getByText('Settings saved')).toBeVisible();
  expect(errors).toEqual([]);
});