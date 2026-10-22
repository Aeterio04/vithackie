import { test, expect, unique } from '../../../runner/fixtures';

test('T02: Signing up with invalid email is rejected', async ({ page }) => {
  await page.goto('/signup');
  await page.getByLabel('Email').fill('not-an-email');
  await page.getByLabel('Password').fill('ValidPass123');
  await page.getByRole('button', { name: 'Sign up' }).click();

  const alert = page.getByRole('alert');
  await expect(alert).toHaveText('Enter a valid email address');
});
