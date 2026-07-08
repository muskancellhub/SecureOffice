import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR } from '../../fixtures/test-data';

test.describe('Network Design Builder', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test('builder page loads', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/\/shop\/designs\/new/, { timeout: 10000 });
  });

  test('builder has input fields for configuration', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    // Check that there are interactive elements (inputs, selects, buttons)
    const inputs = page.locator('input, select, textarea');
    const count = await inputs.count();
    expect(count).toBeGreaterThan(0);
  });
});
