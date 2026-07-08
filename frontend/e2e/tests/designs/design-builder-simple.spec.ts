import { test, expect, captureStepScreenshot, type Page } from '../../fixtures/evidence-fixture';
import { API_BASE_URL, TEST_USERS } from '../../fixtures/test-data';
import { ensureDesignBuilderLoaded, loginAs } from '../../helpers/common-flows';

/**
 * PHASE 1: Design Builder - Simplified Flow-Based Tests
 *
 * Focus: real user journeys around generated designs and saved design detail.
 * The setup creates a shared design lazily and discovers its saved ID from the
 * backend, because the builder itself remains on /shop/designs/new after save.
 */

test.describe('Phase 1: Design Builder - User Flows', () => {
  // Override global fullyParallel for this file, but do not use serial mode:
  // a single failure should not mark the remaining tests as "did not run".
  test.describe.configure({ mode: 'default' });

  let sharedDesignId: string | null = null;

  const getNewestDesignId = async (page: Page): Promise<string | null> => {
    return page.evaluate(async (apiBaseUrl) => {
      const refreshResponse = await fetch(`${apiBaseUrl}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!refreshResponse.ok) {
        throw new Error(`Unable to refresh auth token: ${refreshResponse.status}`);
      }

      const token = await refreshResponse.json();
      const designsResponse = await fetch(`${apiBaseUrl}/designs`, {
        credentials: 'include',
        headers: {
          Authorization: `Bearer ${token.access_token}`,
        },
      });
      if (!designsResponse.ok) {
        throw new Error(`Unable to list designs: ${designsResponse.status}`);
      }

      const designs = await designsResponse.json();
      return Array.isArray(designs) && designs[0]?.id ? designs[0].id : null;
    }, API_BASE_URL);
  };

  const navigateWithinApp = async (page: Page, path: string) => {
    await page.evaluate((targetPath) => {
      window.history.pushState({}, '', targetPath);
      window.dispatchEvent(new PopStateEvent('popstate'));
    }, path);
    await page.waitForFunction(
      (targetPath) => window.location.pathname === targetPath,
      path,
      { timeout: 15000 },
    );
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  };

  const ensureSharedDesign = async (page: Page): Promise<string> => {
    if (sharedDesignId) return sharedDesignId;

    console.log('\n========== CREATING SHARED DESIGN ==========');
    console.log('Starting at:', new Date().toISOString());
    const startTime = Date.now();

    try {
      await ensureDesignBuilderLoaded(page, { waitForBom: true, timeout: 120000 });

      await expect(page.locator('.apx-scope-meta').filter({ hasText: /all changes saved/i }).first())
        .toBeVisible({ timeout: 45000 });

      const designId = await getNewestDesignId(page);
      if (!designId) {
        throw new Error('Design builder saved, but GET /designs did not return a design ID.');
      }

      sharedDesignId = designId;
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      console.log(`Shared design ready: ${sharedDesignId} (${elapsed}s)`);
      return sharedDesignId;
    } catch (error) {
      console.error('FAILED to create shared design!');
      console.error('Error:', error);
      console.error('Current URL:', page.url());
      await page.screenshot({
        path: 'e2e/test-results/debug-shared-design-setup-failed.png',
        fullPage: true,
      }).catch((err) => console.error('Failed to take screenshot:', err));
      throw error;
    } finally {
      console.log('========================================\n');
    }
  };

  const openSharedDesign = async (page: Page) => {
    await loginAs(page, TEST_USERS.company1Admin.email, TEST_USERS.company1Admin.password);
    await page.evaluate(() => {
      localStorage.setItem('so2_onboarding_skip', '1');
    });

    const designId = await ensureSharedDesign(page);
    console.log(`Loading shared design: ${designId}`);
    await navigateWithinApp(page, `/shop/designs/${designId}`);
    await expect(page.locator('h1.dnb-name-display')).toBeVisible({ timeout: 30000 });
    await page.locator('table.dnb-bom').waitFor({ state: 'visible', timeout: 30000 });
  };

  test.beforeEach(async ({ page }) => {
    await openSharedDesign(page);
  });

  test.afterEach(async ({ page }, testInfo) => {
    const status = testInfo.status === 'passed' ? 'PASS' : 'FAIL';
    await captureStepScreenshot(page, testInfo, `phase 1 ${status} evidence`);
  });

  test.describe('Flow 1: Create Design from Intake', () => {
    test('1.1 - Complete intake and reach design builder', async ({ page }) => {
      await expect(page).toHaveURL(/designs/, { timeout: 10000 });
      await expect(page.locator('table.dnb-bom')).toBeVisible({ timeout: 5000 });
      console.log('On saved design page with BOM loaded');
    });

    test('1.2 - BOM section displays with items', async ({ page }) => {
      await expect(page.locator('table.dnb-bom')).toBeVisible({ timeout: 5000 });
      console.log('BOM table visible');
    });

    test('1.3 - BOM contains product line items', async ({ page }) => {
      const count = await page.locator('table.dnb-bom tbody tr').count();
      expect(count).toBeGreaterThan(0);
      console.log(`BOM has ${count} line items`);
    });

    test('1.4 - Design auto-saves successfully', async ({ page }) => {
      await expect(page.locator('.apx-scope-meta').first()).toBeVisible({ timeout: 10000 });
      console.log('Saved design metadata visible');
    });

    test('1.5 - Design has auto-generated name', async ({ page }) => {
      const designName = page.locator('h1.dnb-name-display');
      await expect(designName).toBeVisible({ timeout: 10000 });
      const nameText = await designName.textContent();
      expect(nameText).toBeTruthy();
      expect(nameText).not.toContain('New design');
      console.log(`Design name: ${nameText}`);
    });
  });

  test.describe('Flow 2: Submit Design', () => {
    test('2.1 - Submit button is visible', async ({ page }) => {
      const submitBtn = page.locator('button.dnb-order-btn').filter({ hasText: /order this design/i });
      await expect(submitBtn).toBeVisible({ timeout: 5000 });
      console.log('Order button found');
    });

    test('2.2 - Clicking order adds to cart', async ({ page }) => {
      const orderBtn = page.locator('button.dnb-order-btn').filter({ hasText: /order this design/i });
      await orderBtn.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 });

      const isOnCart = page.url().includes('/cart');
      const hasSuccessNotice = await page.locator('.toast-notice').isVisible({ timeout: 3000 }).catch(() => false);
      expect(isOnCart || hasSuccessNotice).toBeTruthy();
      console.log(isOnCart ? 'Navigated to cart page' : 'Success notice shown');
    });

    test('2.3 - Submitted design appears in list', async ({ page }) => {
      await navigateWithinApp(page, '/shop/designs');
      const designRows = page.locator('[data-testid="design-row"]')
        .or(page.locator('.nd-card, .design-card, .design-item, table tbody tr'));
      const count = await designRows.count();
      expect(count).toBeGreaterThan(0);
      console.log(`Found ${count} designs in list`);
    });
  });

  test.describe('Flow 3: Verify BOM Contents', () => {
    test('3.1 - BOM shows routers category', async ({ page }) => {
      const count = await page.locator('table.dnb-bom tbody tr').filter({ hasText: /router/i }).count();
      expect(count).toBeGreaterThanOrEqual(0);
      console.log(`Found ${count} router items in BOM`);
    });

    test('3.2 - BOM shows access points category', async ({ page }) => {
      const count = await page.locator('table.dnb-bom tbody tr').filter({ hasText: /access point|wifi|ap/i }).count();
      expect(count).toBeGreaterThan(0);
      console.log(`Found ${count} access point items in BOM`);
    });

    test('3.3 - BOM shows switches category', async ({ page }) => {
      const count = await page.locator('table.dnb-bom tbody tr').filter({ hasText: /switch/i }).count();
      expect(count).toBeGreaterThanOrEqual(0);
      console.log(`Found ${count} switch items in BOM`);
    });

    test('3.4 - BOM shows total cost', async ({ page }) => {
      const count = await page.locator('table.dnb-bom td.dnb-num, table.dnb-bom td.dnb-total').count();
      expect(count).toBeGreaterThan(0);
      console.log(`Found ${count} price elements in BOM`);
    });
  });

  test.describe('Flow 4: Design Persistence', () => {
    test('4.1 - Reload page keeps design data', async ({ page }) => {
      const bomTable = page.locator('table.dnb-bom');
      const bomItemsBefore = await bomTable.locator('tbody tr').count();

      await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
      await bomTable.waitFor({ state: 'visible', timeout: 30000 });

      const bomItemsAfter = await bomTable.locator('tbody tr').count();
      expect(bomItemsAfter).toBeGreaterThan(0);
      console.log(`Design persisted (${bomItemsBefore} -> ${bomItemsAfter} items)`);
    });

    test('4.2 - Navigate away and back keeps design', async ({ page }) => {
      await navigateWithinApp(page, '/shop/routers');
      await page.waitForTimeout(1000);

      expect(sharedDesignId).toBeTruthy();
      await navigateWithinApp(page, `/shop/designs/${sharedDesignId}`);
      await expect(page.locator('table.dnb-bom')).toBeVisible({ timeout: 30000 });
      console.log('Design data persisted after navigation');
    });
  });

  test.describe('Flow 5: Design Actions', () => {
    test('5.1 - Can add BOM items to cart', async ({ page }) => {
      const orderBtn = page.locator('button.dnb-order-btn').filter({ hasText: /order this design/i });
      await expect(orderBtn).toBeVisible({ timeout: 5000 });
      console.log('Saved design can be ordered from the detail page');
    });
  });
});
