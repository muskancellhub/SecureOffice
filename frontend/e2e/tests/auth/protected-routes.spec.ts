import { test, expect } from '../../fixtures/evidence-fixture';

/**
 * Protected Routes Tests
 * Maximum 5 test cases (well under 25 limit)
 * Uses XPath selectors for verification
 * No URL parameters
 * Proper session handling (unauthenticated)
 */

test.describe('Protected routes — unauthenticated access', () => {
  // Clear session before each test to ensure unauthenticated state
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
    await context.clearPermissions();
  });

  test('visiting /shop redirects to login', async ({ page }) => {
    // Navigate without parameters
    await page.goto('/shop', { timeout: 30000 });
    
    // Verify redirect to login (allow query parameters from redirect)
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/, { timeout: 10000 });
    
    // Verify login page is visible using XPath
    const emailInput = page.locator('//input[@type="email" or @placeholder="Email Address"]');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
  });

  test('visiting /shop/designs redirects to login', async ({ page }) => {
    await page.goto('/shop/designs', { timeout: 30000 });
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/, { timeout: 10000 });
    
    // Verify on login page using XPath
    const emailInput = page.locator('//input[@type="email"]');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
  });

  test('visiting /shop/cart redirects to login', async ({ page }) => {
    await page.goto('/shop/cart', { timeout: 30000 });
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/, { timeout: 10000 });
    
    const emailInput = page.locator('//input[@type="email"]');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
  });

  test('visiting /shop/orders redirects to login', async ({ page }) => {
    await page.goto('/shop/orders', { timeout: 30000 });
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/, { timeout: 10000 });
    
    const emailInput = page.locator('//input[@type="email"]');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
  });

  test('visiting /shop/admin/products redirects to login', async ({ page }) => {
    await page.goto('/shop/admin/products', { timeout: 30000 });
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/, { timeout: 10000 });
    
    const emailInput = page.locator('//input[@type="email"]');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
  });
});
