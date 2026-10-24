import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T03: Signing up with short password is rejected', async ({ page }) => {
  await page.goto('/signup');
  await page.getByLabel('Email').fill(`${unique('user')}@example.com`);
  await page.getByLabel('Password').fill('1234567');
  await page.getByRole('button', { name: 'Sign up' }).click();
  // S3
  const isInvalid = await page.getByLabel('Password').evaluate((el: HTMLInputElement) => !el.checkValidity() || Boolean(el.validationMessage)).catch(() => false);
  const hasMsg = await page.getByText(/Password must be at least 8 characters/i).isVisible().catch(() => false) || await page.getByRole('alert').isVisible().catch(() => false);
  expect(isInvalid || hasMsg).toBe(true);
  await expect(page).toHaveURL(/\/signup$/);
});