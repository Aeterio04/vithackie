import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T11: Logging out returns to login and Back does not show dashboard', async ({ page }) => {
  // Step 1: Log in and navigate to /dashboard
  await page.goto('/login');
  await page.getByLabel('Email').fill(credentials.username);
  await page.getByLabel('Password').fill(credentials.password);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  // Step 2: Click 'Log out' -> Expected: Navigates to /login
  // S11
  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page).toHaveURL(/\/login$/);

  // Step 3: Click browser Back button -> Expected: Dashboard is not displayed; redirected to /login
  // S11
  await page.goBack();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText('Dashboard')).not.toBeVisible();
});