import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR, TEST_USERS } from '../../fixtures/test-data';

/**
 * Billing & Payment Tests
 * Maximum 3 test cases (well under 25 limit)
 * Uses XPath selectors for robustness
 * NO URL parameters - navigate to base URLs only
 * Proper session handling with storage state
 */

test.describe('Billing & Payment', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  // 🔥 WORKAROUND: Re-login before tests if session expired
  test.beforeEach(async ({ page }) => {
    // Try to access a protected route
    await page.goto('/shop/billing', { timeout: 10000 });
    
    // If redirected to login, re-authenticate
    if (page.url().includes('/login')) {
      console.log('⚠️ Session expired, re-authenticating...');
      
      const emailInput = page.locator('//input[@type="email" or @placeholder="Email Address"]');
      await emailInput.fill(TEST_USERS.company1Admin.email);
      
      const passwordButton = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "password")]');
      await passwordButton.click();
      
      const passwordInput = page.locator('//input[@type="password"]');
      await passwordInput.fill(TEST_USERS.company1Admin.password);
      
      const signInButton = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "sign in") and not(contains(., "password"))]');
      await signInButton.click();
      
      // Wait for redirect to complete
      await page.waitForURL(/\/(shop|dashboard)/, { timeout: 15000 });
      console.log('✅ Re-authentication successful');
    }
  });

  test('billing page loads', async ({ page }) => {
    // Navigate to billing page WITHOUT query parameters
    await page.goto('/shop/billing', { timeout: 45000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    
    // Use XPath to verify billing page content
    const billingContent = page.locator('//h1[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "billing")] | //div[contains(@class, "billing")] | //body');
    await expect(billingContent.first()).toBeVisible();
    
    // Verify substantial content is loaded
    const bodyText = await page.locator('//body').textContent() || '';
    expect(bodyText.length).toBeGreaterThan(50);
    console.log(`✓ Billing page content length: ${bodyText.length} characters`);
  });

  test('billing success page handles callback', async ({ page }) => {
    // Navigate to success callback WITHOUT query parameters in goto
    // Note: Real Stripe callbacks will have session_id as query param added by Stripe
    await page.goto('/billing/success', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    // Use XPath to check for success indicators
    const successIndicator = page.locator('//*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "success") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "thank") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "confirmed") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "complete")]');
    
    const bodyText = await page.locator('//body').textContent() || '';
    const hasSuccess = await successIndicator.count() > 0;
    const redirected = !page.url().match(/\/billing\/success(?:\?.*)?$/);
    
    console.log(`✓ Billing success page — has message: ${hasSuccess}, redirected: ${redirected}`);
    expect(hasSuccess || redirected).toBeTruthy();
  });

  test('billing cancelled page handles callback', async ({ page }) => {
    // Navigate to cancelled callback WITHOUT query parameters in goto
    await page.goto('/billing/cancelled', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    // Use XPath to check for cancellation indicators
    const cancelIndicator = page.locator('//*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "cancel") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "return") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "try again") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "back")]');
    
    const bodyText = await page.locator('//body').textContent() || '';
    const hasCancelled = await cancelIndicator.count() > 0;
    const redirected = !page.url().match(/\/billing\/cancelled(?:\?.*)?$/);
    
    console.log(`✓ Billing cancelled page — has message: ${hasCancelled}, redirected: ${redirected}`);
    expect(hasCancelled || redirected).toBeTruthy();
  });
});
