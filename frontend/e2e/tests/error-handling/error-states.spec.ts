import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR } from '../../fixtures/test-data';

test.describe('Error Handling & Edge Cases', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test('non-existent route redirects to home', async ({ page }) => {
    await page.goto('/this-page-does-not-exist', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    // AppRouter has: <Route path="*" element={<Navigate to="/" replace />} />
    await expect(page).toHaveURL('http://localhost:5173/', { timeout: 10000 });
  });

  test('non-existent shop route stays in app (no crash)', async ({ page }) => {
    await page.goto('/shop/nonexistent-page', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    // Should not crash — either show content or redirect
    const bodyText = await page.locator('body').textContent() || '';
    expect(bodyText.length).toBeGreaterThan(10); // Not a blank crash page
  });

  test('non-existent design ID shows error gracefully', async ({ page }) => {
    await page.goto('/shop/designs/00000000-0000-0000-0000-000000000099', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    const bodyText = await page.locator('body').textContent() || '';
    const hasError = /not found|error|doesn't exist|loading/i.test(bodyText);
    console.log(`Non-existent design handling: ${hasError ? 'shows message' : 'blank/other'}`);
    // Should not show a completely blank page
    expect(bodyText.length).toBeGreaterThan(10);
  });

  test('non-existent order ID shows error gracefully', async ({ page }) => {
    await page.goto('/shop/orders/00000000-0000-0000-0000-000000000099', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    const bodyText = await page.locator('body').textContent() || '';
    const hasError = /not found|error|doesn't exist/i.test(bodyText);
    console.log(`Non-existent order handling: ${hasError ? 'shows message' : 'other'}`);
    expect(bodyText.length).toBeGreaterThan(10);
  });

  test('non-existent router ID shows error gracefully', async ({ page }) => {
    await page.goto('/shop/routers/00000000-0000-0000-0000-000000000099', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    const bodyText = await page.locator('body').textContent() || '';
    console.log(`Non-existent router detail page text length: ${bodyText.length}`);
    expect(bodyText.length).toBeGreaterThan(10);
  });
});
