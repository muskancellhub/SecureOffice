import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR } from '../../fixtures/test-data';

test.describe('Router Catalog', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test('catalog page loads', async ({ page }) => {
    await page.goto('/shop/routers', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/\/shop\/routers/, { timeout: 10000 });
  });

  test('catalog shows products or empty state', async ({ page }) => {
    await page.goto('/shop/routers', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    // Should have either product cards or "no products" message
    const body = await page.locator('body').textContent();
    expect(body!.length).toBeGreaterThan(50); // Not a blank page
  });

  test('managed services page loads', async ({ page }) => {
    await page.goto('/shop/services', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/\/shop\/services/, { timeout: 10000 });
  });
});
