import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T06: Logging in email is case-insensitive', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill('QA.Tester@Example.com');
  await page.getByLabel('Password').fill('Passw0rd!23');
  await page.getByRole('button', { name: 'Log in' }).click();
  // S6
  await expect(page).toHaveURL(/\/dashboard$/);
});