import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T05: Logging in with wrong password shows error', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill('qa.tester@example.com');
  await page.getByLabel('Password').fill('WrongPassword!');
  await page.getByRole('button', { name: 'Log in' }).click();
  // S5
  await expect(page.getByText('Invalid email or password')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});