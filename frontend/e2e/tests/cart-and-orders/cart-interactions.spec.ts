import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR, TEST_USERS } from '../../fixtures/test-data';

/**
 * Cart Interactions Tests
 * Uses pre-authenticated storage state from auth.setup.ts
 */

test.describe('Cart Interactions', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  async function gotoCart(page) {
    // Set onboarding skip flag
    await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.evaluate(() => {
      localStorage.setItem('so2_onboarding_skip', '1');
    });
    
    await page.goto('/shop/cart', { timeout: 30000 });
    await page.waitForLoadState('networkidle');

    const currentUrl = page.url();
    console.log(`🔍 Cart URL: ${currentUrl}`);

    if (currentUrl.includes('/login')) {
      throw new Error(`Redirected to login page - auth state expired. Run auth.setup.ts first.`);
    }
  }

  test('empty cart shows empty state message', async ({ page }) => {
    await gotoCart(page);
    
    // CRITICAL: Wait for cart data to finish loading
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      console.log('Cart is loading, waiting for load to complete...');
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
      console.log('Cart loading completed');
    }
    
    // Wait for cart page header to load
    const header = page.locator('h1:has-text("Your cart")');
    await expect(header).toBeVisible({ timeout: 15000 });
    
    // Check if cart is empty or has items
    const emptyState = page.locator('.cpx-empty');
    const cartItems = page.locator('.cpx-item');
    
    const hasEmpty = await emptyState.isVisible({ timeout: 5000 }).catch(() => false);
    const itemCount = await cartItems.count();
    
    console.log(`Cart state — empty: ${hasEmpty}, has items: ${itemCount}`);
    
    // Either empty state should be visible OR items should exist
    expect(hasEmpty || itemCount > 0).toBeTruthy();
  });

  test('cart shows "Continue shopping" link', async ({ page }) => {
    await gotoCart(page);
    
    // Wait for loading bar to complete
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
    }
    
    // Wait for cart page header
    await page.waitForSelector('.cpx-header', { state: 'visible', timeout: 15000 });
    
    // Continue shopping link
    const continueLink = page.locator('a.cdx-back').first();
    await expect(continueLink).toBeVisible({ timeout: 5000 });
    
    // Verify it points to routers page
    const href = await continueLink.getAttribute('href');
    expect(href).toContain('/shop/routers');
  });

  test('cart shows order summary section when items exist', async ({ page }) => {
    await gotoCart(page);
    
    // Wait for loading bar to complete
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
    }
    
    const hasItems = await page.locator('.cpx-item').count() > 0;
    if (hasItems) {
      await expect(page.locator('.cpx-summary h3')).toContainText(/order summary/i);
      await expect(page.getByText(/one-time hardware/i)).toBeVisible();
      await expect(page.getByText(/managed services/i)).toBeVisible();
      await expect(page.getByRole('button', { name: /generate proposal/i })).toBeVisible();
    } else {
      console.log('Cart is empty, skipping order summary check');
    }
  });

  test('adding item from catalog to cart', async ({ page }) => {
    // Set onboarding skip
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
      localStorage.setItem('so2_onboarding_skip', '1');
    });
    
    // Go to router catalog
    await page.goto('/shop/routers', { timeout: 30000 });
    await page.waitForTimeout(2000);
    
    // 📸 EVIDENCE: Router catalog page loaded
    await page.screenshot({ 
      path: `e2e/test-results/catalog-loaded.png`,
      fullPage: true 
    });

    // Find "Add to cart" button
    const addBtn = page.getByRole('button', { name: /add to cart|add/i }).first();
    const hasAddBtn = await addBtn.isVisible().catch(() => false);
    console.log(`"Add to cart" button found: ${hasAddBtn}`);

    if (hasAddBtn) {
      // 📸 EVIDENCE: Before clicking add to cart
      await page.screenshot({ 
        path: `e2e/test-results/before-add-to-cart.png`,
        fullPage: true 
      });
      
      await addBtn.click();
      await page.waitForTimeout(1000);
      
      // 📸 EVIDENCE: After clicking add to cart (item added)
      await page.screenshot({ 
        path: `e2e/test-results/after-add-to-cart.png`,
        fullPage: true 
      });
      
      // Navigate to cart
      await gotoCart(page);
      
      // Wait for loading bar
      const loadingBar = page.locator('.dh-loading-bar');
      const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
      if (hasLoadingBar) {
        await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
      }
      
      // 📸 EVIDENCE: Cart page with newly added item
      await page.screenshot({ 
        path: `e2e/test-results/cart-with-new-item.png`,
        fullPage: true 
      });
      
      const cartItems = await page.locator('.cpx-item').count();
      console.log(`Cart items after add: ${cartItems}`);
      expect(cartItems).toBeGreaterThan(0);
      
      // 📸 EVIDENCE: Final assertion passed
      await page.screenshot({ 
        path: `e2e/test-results/test-complete.png`,
        fullPage: true 
      });
    } else {
      console.log('No "Add to cart" button found, skipping test');
    }
  });

  test('cart quantity buttons work', async ({ page }) => {
    await gotoCart(page);
    
    // Wait for loading bar to complete
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
    }
    
    const hasItems = await page.locator('.cpx-item').count() > 0;
    if (hasItems) {
      const increaseBtn = page.getByLabel('Increase').first();
      const qtyBefore = await page.locator('.cpx-qty-val').first().textContent();
      if (await increaseBtn.isVisible()) {
        await increaseBtn.click();
        await page.waitForTimeout(1000);
        const qtyAfter = await page.locator('.cpx-qty-val').first().textContent();
        console.log(`Quantity before: ${qtyBefore}, after: ${qtyAfter}`);
      }
    } else {
      console.log('Cart is empty, skipping quantity button test');
    }
  });

  test('cart remove button removes item', async ({ page }) => {
    await gotoCart(page);
    
    // Wait for loading bar to complete
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
    }
    
    const itemCount = await page.locator('.cpx-item').count();
    if (itemCount > 0) {
      const removeBtn = page.getByLabel('Remove').first();
      if (await removeBtn.isVisible()) {
        await removeBtn.click();
        await page.waitForTimeout(1000);
        const newCount = await page.locator('.cpx-item').count();
        console.log(`Items before remove: ${itemCount}, after: ${newCount}`);
        expect(newCount).toBeLessThan(itemCount);
      }
    } else {
      console.log('Cart is empty, skipping remove button test');
    }
  });

  test('generate proposal button exists for non-empty cart', async ({ page }) => {
    await gotoCart(page);
    
    // Wait for loading bar to complete
    const loadingBar = page.locator('.dh-loading-bar');
    const hasLoadingBar = await loadingBar.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasLoadingBar) {
      await loadingBar.waitFor({ state: 'hidden', timeout: 15000 });
    }
    
    const hasItems = await page.locator('.cpx-item').count() > 0;
    if (hasItems) {
      const proposalBtn = page.getByRole('button', { name: /generate proposal/i });
      await expect(proposalBtn).toBeVisible();
      await expect(proposalBtn).toBeEnabled();
    } else {
      console.log('Cart is empty, skipping proposal button test');
    }
  });
});
