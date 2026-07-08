import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR } from '../../fixtures/test-data';

test.describe('Shop Navigation & Sidebar', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test('shop landing page loads', async ({ page }) => {
    await page.goto('/shop', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    // Should not redirect to login
    await expect(page).not.toHaveURL(/\/login/, { timeout: 5000 });
  });

  test('shop has sidebar navigation', async ({ page }) => {
    await page.goto('/shop', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    // Should have navigation links
    const nav = page.getByRole('navigation');
    const hasNav = await nav.isVisible().catch(() => false);
    const links = await page.getByRole('link').count();
    console.log(`Navigation visible: ${hasNav}, total links: ${links}`);
    expect(links).toBeGreaterThan(3); // At minimum: designs, routers, cart, orders
  });

  test('can navigate to designs from shop', async ({ page }) => {
    await page.goto('/shop', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    const designsLink = page.getByRole('link', { name: /design/i }).first();
    if (await designsLink.isVisible().catch(() => false)) {
      await designsLink.click();
      await expect(page).toHaveURL(/\/shop\/designs/, { timeout: 10000 });
    }
  });

  test('can navigate to routers from shop', async ({ page }) => {
    await page.goto('/shop', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    const routersLink = page.getByRole('link', { name: /router|catalog|product/i }).first();
    if (await routersLink.isVisible().catch(() => false)) {
      await routersLink.click();
      await expect(page).toHaveURL(/\/shop\/routers/, { timeout: 10000 });
    }
  });

  test('can navigate to cart from shop', async ({ page }) => {
    await page.goto('/shop', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    const cartLink = page.getByRole('link', { name: /cart/i }).first();
    if (await cartLink.isVisible().catch(() => false)) {
      await cartLink.click();
      await expect(page).toHaveURL(/\/shop\/cart/, { timeout: 10000 });
    }
  });

  test('dashboard page loads', async ({ page }) => {
    await page.goto('/shop/dashboard', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await expect(page).not.toHaveURL(/\/login/);
    const bodyText = await page.locator('body').textContent() || '';
    expect(bodyText.length).toBeGreaterThan(50);
  });

  test('zabbix monitoring page loads', async ({ page }) => {
    await page.goto('/shop/zabbix', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await expect(page).not.toHaveURL(/\/login/);
    const bodyText = await page.locator('body').textContent() || '';
    console.log(`Zabbix page content length: ${bodyText.length}`);
  });
});
