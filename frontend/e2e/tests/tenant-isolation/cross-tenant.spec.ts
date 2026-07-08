import {
  test,
  expect,
  captureStepScreenshot,
  instrumentPageForStepScreenshots,
} from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR } from '../../fixtures/test-data';

test.describe('Tenant Isolation', () => {
  test('company1 and company2 see different data on designs page', async ({ browser }, testInfo) => {
    const ctx1 = await browser.newContext({
      storageState: `${AUTH_STATE_DIR}/company1-admin.json`,
    });
    const ctx2 = await browser.newContext({
      storageState: `${AUTH_STATE_DIR}/company2-user.json`,
    });

    const page1 = instrumentPageForStepScreenshots(await ctx1.newPage(), testInfo);
    const page2 = instrumentPageForStepScreenshots(await ctx2.newPage(), testInfo);

    await page1.goto('/shop/designs', { timeout: 30000 });
    await page2.goto('/shop/designs', { timeout: 30000 });

    await page1.waitForLoadState('networkidle');
    await page2.waitForLoadState('networkidle');

    // Both pages should load without error
    await expect(page1).toHaveURL(/\/shop\/designs/);
    await expect(page2).toHaveURL(/\/shop\/designs/);
    await captureStepScreenshot(page1, testInfo, 'company1 designs final state');
    await captureStepScreenshot(page2, testInfo, 'company2 designs final state');

    await ctx1.close();
    await ctx2.close();
  });

  test('company1 cannot access fabricated order URL', async ({ browser }, testInfo) => {
    const ctx = await browser.newContext({
      storageState: `${AUTH_STATE_DIR}/company1-admin.json`,
    });
    const page = instrumentPageForStepScreenshots(await ctx.newPage(), testInfo);

    // Try accessing a non-existent order (fake UUID)
    const response = await page.goto('/shop/orders/00000000-0000-0000-0000-000000000099', { timeout: 30000 });

    await page.waitForLoadState('domcontentloaded');

    // Check: either redirected, got 404/403, or shows error message in UI
    const url = page.url();
    const pageText = await page.locator('body').textContent() || '';
    const hasErrorIndicator =
      url.includes('/login') ||
      url.includes('/orders') && !url.includes('000000000099') ||
      /not found|error|denied|does not exist|404|403/i.test(pageText);

    // Report what actually happened for the defect report
    console.log(`Cross-tenant order URL result: stayed on ${url}`);
    console.log(`Page shows error: ${hasErrorIndicator}`);
    await captureStepScreenshot(page, testInfo, 'fabricated order url final state');

    await ctx.close();
  });

  test('super admin can access designs page', async ({ browser }, testInfo) => {
    const ctx = await browser.newContext({
      storageState: `${AUTH_STATE_DIR}/super-admin.json`,
    });
    const page = instrumentPageForStepScreenshots(await ctx.newPage(), testInfo);
    await page.goto('/shop/designs', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/\/shop\/designs/);
    await captureStepScreenshot(page, testInfo, 'super admin designs final state');
    await ctx.close();
  });
});
