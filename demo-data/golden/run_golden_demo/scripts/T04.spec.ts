import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T04: Logging in with valid credentials lands on dashboard', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill(credentials.username);
  await page.getByLabel('Password').fill(credentials.password);
  await page.getByRole('button', { name: 'Log in' }).click();
  // S4
  await expect(page).toHaveURL(/\/dashboard$/);
});