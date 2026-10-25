import { test, expect } from '../../apps/runner/fixtures';

test.describe('QA Benchmark Probes', () => {

  test.beforeEach(async ({ context }) => {
    const sessionId = 'probe-' + Math.random().toString(36).substring(2, 10);
    await context.setExtraHTTPHeaders({
      'x-session-id': sessionId,
    });
  });

  // P01: Login with invalid password (K1: Different wording from spec)
  // Expected in Clean: PASS (displays "Incorrect email or password")
  // Expected in Buggy (B1): FAIL (no error displayed)
  test('P01 login invalid password shows error', async ({ page }) => {
    await page.goto('/login');
    await page.fill('#email', 'seed.user@example.com');
    await page.fill('#password', 'WrongPassword999!');
    await page.click('#login-submit');

    const toast = page.locator('#login-error-toast');
    await expect(toast).toBeVisible({ timeout: 5000 });
    const text = (await toast.textContent()) || '';
    expect(text.toLowerCase()).toMatch(/incorrect|invalid|wrong|error/);
  });

  // P02: Delayed error toast (K2: 1.5s delay)
  // Expected in Clean: PASS
  // Expected in Buggy (B1): FAIL
  test('P02 login error toast delayed appearance', async ({ page }) => {
    await page.goto('/login');
    await page.fill('#email', 'qa.tester@example.com');
    await page.fill('#password', 'BadSecret123');
    await page.click('#login-submit');

    const toast = page.locator('#login-error-toast');
    // Must wait through the 1.5s delay to be visible
    await expect(toast).toBeVisible({ timeout: 6000 });
    await expect(toast).toContainText('Incorrect email or password');
  });

  // P03: Native HTML5 email validation (K3: browser bubble, validity.typeMismatch / !valid)
  // Expected in Clean: PASS (validity.valid is false)
  // Expected in Buggy (B3): FAIL (server accepts invalid email or validity is true)
  test('P03 signup malformed email native validation', async ({ page }) => {
    await page.goto('/signup');
    await page.fill('#name', 'Probe Tester');
    const emailInput = page.locator('#email');
    await emailInput.fill('invalid-email-without-at');
    await page.fill('#password', 'Password123!');

    const isValid = await emailInput.evaluate((el: HTMLInputElement) => el.validity.valid);
    expect(isValid).toBe(false);

    // Clicking submit must not navigate away or succeed
    await page.click('#signup-submit');
    await page.waitForTimeout(500);
    expect(page.url()).toContain('/signup');
  });

  // P04: Open Shadow DOM promo code validation (K4)
  // Expected in Clean: PASS
  test('P04 shadow root promo code error feedback', async ({ page }) => {
    await page.goto('/cart');
    // Discount box is a custom element with open shadow root
    const promoInput = page.locator('discount-box').locator('input#code');
    await promoInput.fill('BADCODE99');
    const applyBtn = page.locator('discount-box').locator('button#apply-btn');
    await applyBtn.click();

    const feedback = page.locator('discount-box').locator('#discount-feedback');
    await expect(feedback).toBeVisible({ timeout: 3000 });
    await expect(feedback).toContainText('Invalid discount coupon code');
  });

  // P05: Iframe support desk feedback (K4)
  // Expected in Clean: PASS
  test('P05 iframe support desk offline message', async ({ page }) => {
    await page.goto('/cart');
    const frame = page.frameLocator('#support-frame');
    await frame.locator('#query').fill('Where is my package?');
    await frame.locator('button[type="submit"]').click();

    const msg = frame.locator('#iframe-err');
    await expect(msg).toBeVisible({ timeout: 3000 });
    await expect(msg).toContainText('Support desk is temporarily offline');
  });

  // P06: Empty cart checkout blocked (K5)
  // Expected in Clean: PASS
  test('P06 empty cart checkout correctly blocked', async ({ page }) => {
    // Reset session cart first
    await page.request.post('/api/reset');
    await page.goto('/checkout');
    await page.click('#checkout-submit-btn');

    const feedback = page.locator('#checkout-feedback');
    await expect(feedback).toBeVisible({ timeout: 3000 });
    await expect(feedback).toContainText('Your cart is empty');
  });

  // P07: Cart subtotal with quantity > 1 (B2: cart-total-wrong)
  // Expected in Clean: PASS
  // Expected in Buggy (B2): FAIL
  test('P07 cart subtotal multi quantity calculation', async ({ page }) => {
    await page.request.post('/api/reset');
    // Add product 1 ($99.99) with quantity 2
    await page.request.post('/api/cart', {
      data: { productId: '1', quantity: 2 }
    });

    await page.goto('/cart');
    const subtotalEl = page.locator('[data-testid="cart-subtotal"]');
    await expect(subtotalEl).toBeVisible();
    const text = await subtotalEl.textContent();
    // 99.99 * 2 = 199.98
    expect(text).toContain('199.98');
  });

  // P08: Cart tax calculation 10% (K5)
  // Expected in Clean: PASS
  // Expected in Buggy (B2): FAIL
  test('P08 cart tax calculation accuracy', async ({ page }) => {
    await page.request.post('/api/reset');
    // Add product 1 ($99.99) quantity 1
    await page.request.post('/api/cart', {
      data: { productId: '1', quantity: 1 }
    });

    await page.goto('/cart');
    const taxEl = page.locator('[data-testid="cart-tax"]');
    await expect(taxEl).toBeVisible();
    const text = await taxEl.textContent();
    // 99.99 * 0.10 = 10.00
    expect(text).toContain('10.00');
  });

  // P09: Checkout order placement (B4: checkout-500)
  // Expected in Clean: PASS (200 OK + alert with order id)
  // Expected in Buggy (B4): FAIL (HTTP 500)
  test('P09 checkout order placement with items', async ({ page }) => {
    await page.request.post('/api/reset');
    await page.request.post('/api/cart', {
      data: { productId: '4', quantity: 1 }
    });

    await page.goto('/checkout');
    let dialogAppeared = false;
    let dialogMessage = '';
    page.on('dialog', async (dialog) => {
      dialogAppeared = true;
      dialogMessage = dialog.message();
      await dialog.accept();
    });

    const [response] = await Promise.all([
      page.waitForResponse((res) => res.url().includes('/api/checkout')),
      page.click('#checkout-submit-btn')
    ]);

    expect(response.status()).toBe(200);
    const json = await response.json();
    expect(json.ok).toBe(true);
    expect(json.orderId).toMatch(/^ORD-\d+/);
  });

  // P10: Product page clean console / no uncaught exception (B5: silent-console-error)
  // Expected in Clean: PASS
  // Expected in Buggy (B5): FAIL (console error / uncaught TypeError in telemetry)
  test('P10 product page clean console telemetry', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await page.goto('/products/1');
    await page.waitForTimeout(500); // Wait for DOMContentLoaded telemetry callback

    expect(pageErrors.length).toBe(0);
  });

  // P11: Catalog price formatting (B8: price-format NaN)
  // Expected in Clean: PASS
  // Expected in Buggy (B8): FAIL ($NaN detected)
  test('P11 catalog prices valid formatting', async ({ page }) => {
    await page.goto('/');
    const prices = await page.locator('.product-price').allTextContents();
    expect(prices.length).toBeGreaterThan(0);
    for (const p of prices) {
      expect(p).not.toContain('NaN');
      expect(p).toMatch(/^\$\d+(\.\d{2})?$/);
    }
  });

  // P12: Catalog image integrity (B6: broken-image 404)
  // Expected in Clean: PASS
  // Expected in Buggy (B6): FAIL (404 image load)
  test('P12 catalog image integrity', async ({ page }) => {
    const failedImages: string[] = [];
    page.on('response', (res) => {
      if (res.request().resourceType() === 'image' && res.status() >= 400) {
        failedImages.push(res.url());
      }
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(failedImages.length).toBe(0);
  });
});
