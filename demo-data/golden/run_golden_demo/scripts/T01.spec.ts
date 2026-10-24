import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T01: Signing up with valid credentials lands on dashboard', async ({ page }) => {
  await page.goto('/signup');
  await page.getByLabel('Email').fill(`${unique('user')}@example.com`);
  await page.getByLabel('Password').fill('Passw0rd!123');
  await page.getByRole('button', { name: 'Sign up' }).click();
  // S1
  await expect(page).toHaveURL(/\/dashboard$/);
});