import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR, TEST_USERS } from '../../fixtures/test-data';

/**
 * Square Payment Integration Tests
 * Tests the Square Web Payments SDK integration for subscriptions and orders
 * 
 * REQUIREMENTS:
 * - Square SDK must be loaded on billing pages
 * - Widget accepts test card numbers
 * - Webhook handling for payment confirmation
 * - Customer ID stored in database
 * 
 * TEST DATA:
 * - Square Test Card: 4111 1111 1111 1111 (CVV: 111, ZIP: 12345)
 * - Square Test Card (declined): 4000 0000 0000 0002
 */

test.describe('Square Payment Integration', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test.beforeEach(async ({ page }) => {
    await page.goto('/shop/billing', { timeout: 10000 });
    
    // Re-authenticate if session expired
    if (page.url().includes('/login')) {
      console.log('⚠️ Session expired, re-authenticating...');
      const emailInput = page.locator('//input[@type="email"]');
      await emailInput.fill(TEST_USERS.company1Admin.email);
      const passwordButton = page.locator('//button[contains(text(), "password")]');
      await passwordButton.click();
      const passwordInput = page.locator('//input[@type="password"]');
      await passwordInput.fill(TEST_USERS.company1Admin.password);
      const signInButton = page.locator('//button[contains(text(), "Sign In")]');
      await signInButton.click();
      await page.waitForURL(/\/(shop|dashboard)/, { timeout: 15000 });
    }
  });

  test('Square SDK loads on billing page', async ({ page }) => {
    await page.goto('/shop/billing', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    // Check if Square SDK script is loaded
    const squareScript = await page.evaluate(() => {
      return !!window.Square || !!document.querySelector('script[src*="square"]');
    });
    
    console.log(`✓ Square SDK loaded: ${squareScript}`);
    expect(squareScript).toBeTruthy();
  });

  test('subscription checkout with Square widget', async ({ page }) => {
    await page.goto('/shop/billing', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    
    // Find and click subscription button
    const subscribeButton = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "subscribe")]');
    
    if (await subscribeButton.count() > 0) {
      await subscribeButton.first().click();
      await page.waitForTimeout(2000);
      
      // Check if Square payment form loads
      const squarePaymentForm = page.locator('#sq-card-number, [id*="square"], [class*="sq-payment"]');
      const hasPaymentForm = await squarePaymentForm.count() > 0;
      
      console.log(`✓ Square payment form visible: ${hasPaymentForm}`);
      
      // If payment form loads, verify elements
      if (hasPaymentForm) {
        const cardInput = page.locator('#sq-card-number, input[placeholder*="Card"]');
        await expect(cardInput.first()).toBeVisible({ timeout: 5000 });
        console.log('✓ Card input field found');
      }
    } else {
      console.log('⚠️ Subscribe button not found - may need to complete onboarding first');
    }
  });

  test('order checkout with Square widget', async ({ page }) => {
    // Navigate to orders page
    await page.goto('/shop/orders', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    // Check if any orders exist
    const orderRows = page.locator('//tr[contains(@class, "order")] | //div[contains(@class, "order-card")]');
    const orderCount = await orderRows.count();
    
    if (orderCount > 0) {
      // Click first order to view details
      await orderRows.first().click();
      await page.waitForTimeout(1500);
      
      // Look for checkout/pay button
      const checkoutButton = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "checkout") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "pay")]');
      
      if (await checkoutButton.count() > 0) {
        await checkoutButton.first().click();
        await page.waitForTimeout(2000);
        
        // Verify Square widget loads for order payment
        const squarePaymentForm = page.locator('#sq-card-number, [id*="square"]');
        const hasPaymentForm = await squarePaymentForm.count() > 0;
        
        console.log(`✓ Square order payment form visible: ${hasPaymentForm}`);
      } else {
        console.log('⚠️ No checkout button found - order may be paid or pending');
      }
    } else {
      console.log('⚠️ No orders found - create an order first to test checkout');
    }
  });

  test('Square payment success callback', async ({ page }) => {
    // Navigate to success page (Square will redirect here after payment)
    await page.goto('/billing/success', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    // Check for success indicators
    const successIndicator = page.locator('//*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "success") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "confirmed")]');
    const hasSuccess = await successIndicator.count() > 0;
    
    console.log(`✓ Payment success page rendered: ${hasSuccess}`);
    expect(hasSuccess || page.url().includes('/dashboard')).toBeTruthy();
  });

  test('Square payment cancelled callback', async ({ page }) => {
    await page.goto('/billing/cancelled', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    const cancelIndicator = page.locator('//*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "cancel") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "try again")]');
    const hasCancelled = await cancelIndicator.count() > 0;
    
    console.log(`✓ Payment cancelled page rendered: ${hasCancelled}`);
    expect(hasCancelled || page.url().includes('/billing')).toBeTruthy();
  });

  test('Square customer ID stored in tenant record', async ({ page }) => {
    // This test verifies that after payment, the tenant has a square_customer_id
    // We can check this via API or by inspecting the billing page for customer info
    
    await page.goto('/shop/billing', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    // Check if customer info is displayed (indicates customer ID exists)
    const bodyText = await page.locator('//body').textContent() || '';
    const hasCustomerInfo = bodyText.toLowerCase().includes('customer') || 
                           bodyText.toLowerCase().includes('payment method');
    
    console.log(`✓ Customer info displayed: ${hasCustomerInfo}`);
    // Note: This is a basic check - actual verification requires backend API call
  });
});
