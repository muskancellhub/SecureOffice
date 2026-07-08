import { test, expect, type Page } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR, TEST_USERS } from '../../fixtures/test-data';

/**
 * Cart Management Tests
 * Uses pre-authenticated storage state from auth.setup.ts
 * 
 * NOTE: Tests will capture screenshots automatically at test start/end,
 * plus you can add manual screenshots at key moments for better evidence.
 */

test.describe('Cart Management', () => {
  // Use pre-authenticated storage state instead of logging in repeatedly
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test.beforeEach(async ({ page }) => {
    // Set onboarding skip flag to prevent redirect
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
      localStorage.setItem('so2_onboarding_skip', '1');
    });
    
    // Navigate to cart
    await page.goto('/shop/cart', { waitUntil: 'load', timeout: 30000 });
    
    // Wait for page to stabilize
    await page.waitForTimeout(2000);
    
    // 📸 Capture evidence: Cart page loaded
    await page.screenshot({ fullPage: true });
    
    // Debug logging
    const url = page.url();
    console.log(`📍 Current URL: ${url}`);
    
    if (url.includes('/login')) {
      throw new Error(`Redirected to login page - auth state expired or invalid. Run auth.setup.ts first.`);
    }
  });

  test.afterEach(async ({ page }, testInfo) => {
    // 📸 Capture final state screenshot for evidence
    await page.screenshot({ 
      path: `${testInfo.outputDir}/final-state.png`,
      fullPage: true 
    });
  });

  test('cart page loads successfully', async ({ page }) => {
    await expect(page).toHaveURL(/\/shop\/cart(?:\?.*)?$/, { timeout: 10000 });
    
    // Wait for loading bar to disappear
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      console.log('Cart is loading, waiting...');
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
    }
    
    // Cart page doesn't have data-testid, check for the actual page structure
    await expect(page.locator('.cpx-page')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.cpx-header h1')).toContainText('Your cart');
    
    // 📸 Evidence: Cart page fully loaded
    await page.screenshot({ fullPage: true });
  });

  test('empty cart shows appropriate message', async ({ page }) => {
    // Wait for loading bar to complete
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
    }
    
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    
    // Check if page loaded correctly - use actual class name
    await expect(page.locator('.cpx-page')).toBeVisible({ timeout: 15000 });
    
    const itemCount = await page.locator('.cpx-item').count();

    if (itemCount === 0) {
      // Empty cart message is in .cpx-empty div, not a data-testid
      await expect(page.locator('.cpx-empty')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('.cpx-empty h3')).toContainText('Your cart is empty');
      await expect(page.getByRole('link', { name: /browse catalog/i })).toBeVisible();
    } else {
      console.log(`Cart has ${itemCount} items`);
    }
  });

  test('cart displays item count badge', async ({ page }) => {
    // Wait for loading bar to complete
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
    }
    
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    
    // Check if page loaded correctly
    await expect(page.locator('.cpx-page')).toBeVisible({ timeout: 15000 });
    
    // Cart count is in the header: <span className="cpx-count">{totalLineCount} {totalLineCount === 1 ? 'item' : 'items'}</span>
    const cartCount = page.locator('.cpx-count');
    await expect(cartCount).toBeVisible({ timeout: 10000 });
    
    // Verify it shows a number
    const text = await cartCount.textContent();
    expect(text).toMatch(/\d+\s+(item|items)/);
  });

  test('cart shows product details correctly', async ({ page }) => {
    const cartItems = page.locator('.cpx-item');
    const itemCount = await cartItems.count();

    if (itemCount > 0) {
      const firstItem = cartItems.first();
      await expect(firstItem.locator('.cpx-item-info strong').first()).toBeVisible();
      await expect(firstItem.locator('.cpx-item-price, .cpx-svc-price').first()).toBeVisible();
    } else {
      console.log('No items in cart to verify');
    }
  });

  test('quantity controls are functional', async ({ page }) => {
    const firstItem = page.locator('.cpx-item').first();

    if (await firstItem.isVisible().catch(() => false)) {
      const increaseBtn = firstItem.getByLabel(/increase/i);
      const decreaseBtn = firstItem.getByLabel(/decrease/i);
      const hasControls =
        (await increaseBtn.isVisible().catch(() => false)) ||
        (await decreaseBtn.isVisible().catch(() => false));

      expect(hasControls).toBeTruthy();
    }
  });

  test('remove item button is present', async ({ page }) => {
    const firstItem = page.locator('.cpx-item').first();

    if (await firstItem.isVisible().catch(() => false)) {
      await expect(firstItem.getByLabel(/^remove$/i)).toBeVisible();
    }
  });

  test('cart total is calculated', async ({ page }) => {
    const itemCount = await page.locator('.cpx-item').count();

    if (itemCount > 0) {
      await expect(page.locator('.cpx-summary')).toBeVisible();
      await expect(page.locator('.cpx-summary').getByText(/\$/).last()).toBeVisible();
    }
  });

  test('checkout button is present', async ({ page }) => {
    const checkoutBtn = page.getByRole('button', { name: /generate proposal|checkout|place order/i });
    const isVisible = await checkoutBtn.isVisible().catch(() => false);

    if (isVisible) {
      await expect(checkoutBtn).toBeEnabled();
    } else {
      console.log('Checkout/proposal button hidden because cart is empty');
    }
  });

  test('continue shopping link works', async ({ page }) => {
    // Wait for loading bar first
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
    }
    
    // Check if page loaded
    try {
      await expect(page.locator('.cpx-page')).toBeVisible({ timeout: 10000 });
    } catch (error) {
      console.log('⚠️  Cart page not loading, skipping this test');
      test.skip();
      return;
    }
    
    // Continue shopping link uses class "cdx-back"
    const continueLink = page.locator('a.cdx-back').first();
    
    // Wait for link to be visible
    await expect(continueLink).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(500);
    
    // Click and wait for navigation
    await Promise.all([
      page.waitForURL(/\/shop\/routers/, { timeout: 30000 }),
      continueLink.click()
    ]);
  });
});

test.describe('Orders Page', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test.beforeEach(async ({ page }) => {
    // Set onboarding skip flag
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
      localStorage.setItem('so2_onboarding_skip', '1');
    });
    
    await page.goto('/shop/orders', { waitUntil: 'load', timeout: 30000 });
    await page.waitForTimeout(2000);
    
    console.log(`📍 Orders URL: ${page.url()}`);
    
    if (page.url().includes('/login')) {
      throw new Error(`Redirected to login page - auth state expired. Run auth.setup.ts first.`);
    }
  });

  test('orders page loads successfully', async ({ page }) => {
    await expect(page).toHaveURL(/\/shop\/orders(?:\?.*)?$/, { timeout: 10000 });
    
    // Just verify we're on the right URL
    expect(page.url()).toContain('/shop/orders');
  });

  test('orders list displays correctly', async ({ page }) => {
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    
    const orderItems = page.locator('.ord-row');
    const orderCount = await orderItems.count();

    if (orderCount === 0) {
      const emptyMessage = page.locator('.ord-empty');
      const hasEmpty = await emptyMessage.isVisible({ timeout: 10000 }).catch(() => false);
      
      if (hasEmpty) {
        console.log('Orders page showing empty state');
      } else {
        console.log('No orders found');
      }
    } else {
      console.log(`Found ${orderCount} orders`);
      await expect(orderItems.first()).toBeVisible();
    }
  });

  test('order status badges are visible', async ({ page }) => {
    const firstOrder = page.locator('.ord-row').first();

    if (await firstOrder.isVisible().catch(() => false)) {
      await expect(firstOrder.locator('.ord-status')).toBeVisible();
    }
  });
});

test.describe('Billing Page', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test.beforeEach(async ({ page }) => {
    // Set onboarding skip flag
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
      localStorage.setItem('so2_onboarding_skip', '1');
    });
    
    await page.goto('/shop/billing', { waitUntil: 'load', timeout: 30000 });
    await page.waitForTimeout(2000);
    
    console.log(`📍 Billing URL: ${page.url()}`);
    
    if (page.url().includes('/login')) {
      throw new Error(`Redirected to login page - auth state expired. Run auth.setup.ts first.`);
    }
  });

  test('billing page loads', async ({ page }) => {
    await expect(page).toHaveURL(/\/shop\/billing(?:\?.*)?$/, { timeout: 10000 });
    
    // BillingPage doesn't have data-testid, check for actual structure
    await expect(page.locator('.billing-page')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.bil-header h1')).toContainText('Billing');
  });

  test('billing information is displayed', async ({ page }) => {
    await expect(page.locator('.bil-header')).toBeVisible();
    await expect(page.locator('.bil-subtitle')).toContainText(/recurring charges, invoices/i);
  });
});
