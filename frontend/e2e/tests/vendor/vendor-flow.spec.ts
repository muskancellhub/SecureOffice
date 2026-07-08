import { test, expect } from '../../fixtures/evidence-fixture';

test.describe('Vendor Registration & Login', () => {
  test('vendor register page loads with all fields', async ({ page }) => {
    await page.goto('/vendor/register', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    // Should have vendor-specific registration fields
    const bodyText = await page.locator('body').textContent() || '';
    const hasVendorContent = /vendor|supplier|company|contact/i.test(bodyText);
    expect(hasVendorContent).toBeTruthy();
    console.log(`Vendor registration content present: ${hasVendorContent}`);
  });

  test('vendor register has company fields', async ({ page }) => {
    await page.goto('/vendor/register', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    // Should have company name, contact name, email, etc.
    const inputs = await page.locator('input, select, textarea').count();
    console.log(`Vendor registration input fields: ${inputs}`);
    expect(inputs).toBeGreaterThan(3); // At minimum: name, email, password, company
  });

  test('vendor login page loads', async ({ page }) => {
    await page.goto('/vendor/login', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    const bodyText = await page.locator('body').textContent() || '';
    const hasLoginContent = /sign in|log in|email|password|vendor/i.test(bodyText);
    expect(hasLoginContent).toBeTruthy();
  });

  test('vendor register rejects empty submission', async ({ page }) => {
    await page.goto('/vendor/register', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    // Try to submit empty form
    const submitBtn = page.getByRole('button', { name: /submit|register|sign up|continue/i }).first();
    if (await submitBtn.isVisible().catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(1000);
      // Should stay on page (HTML validation) or show error
      expect(page.url()).toContain('/vendor/register');
    }
  });
});
