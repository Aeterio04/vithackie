import { test, expect, credentials, unique } from '../../../apps/runner/fixtures';

test('T02: Signing up with invalid email is rejected', async ({ page }) => {
  await page.goto('/signup');
  await page.getByLabel('Email').fill('not-an-email');
  await page.getByLabel('Password').fill('ValidPass123');
  await page.getByRole('button', { name: 'Sign up' }).click();
  // S2
  const isInvalid = await page.getByLabel('Email').evaluate((el: HTMLInputElement) => !el.checkValidity() || Boolean(el.validationMessage)).catch(() => false);
  const hasMsg = await page.getByText(/valid email/i).isVisible().catch(() => false) || await page.getByRole('alert').isVisible().catch(() => false);
  expect(isInvalid || hasMsg).toBe(true);
  await expect(page).toHaveURL(/\/signup$/);
});