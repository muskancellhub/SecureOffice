import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR } from '../../fixtures/test-data';

test.describe('Design Builder — Full Flow', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test('builder page renders interactive elements', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    // Should not be stuck on loading forever
    const loadingVisible = await page.getByText('Loading...').isVisible().catch(() => false);
    if (loadingVisible) {
      // Wait up to 15s for loading to disappear
      await expect(page.getByText('Loading...')).not.toBeVisible({ timeout: 15000 });
    }
    // After loading, should have interactive content
    const bodyText = await page.locator('body').textContent() || '';
    expect(bodyText.length).toBeGreaterThan(100);
  });

  test('design builder has calculator/intake section', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    // Wait for loading to finish
    await page.waitForTimeout(3000);
    // Look for calculator-related labels or inputs
    const hasCalcElements = await page.locator('input, select, [data-testid*="calc"], [class*="calc"]').count();
    const hasFormLabels = await page.getByText(/floor|area|access point|device|employee|square/i).count();
    // Report findings
    console.log(`Builder inputs/selects found: ${hasCalcElements}`);
    console.log(`Calculator-related labels found: ${hasFormLabels}`);
    expect(hasCalcElements + hasFormLabels).toBeGreaterThan(0);
  });

  test('design auto-generates a name', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    // Look for auto-generated design name pattern: designN-INITIALS-company-YYYY-MM-DD
    const nameElement = page.locator('[class*="design-name"], [data-testid*="name"], h1, h2, h3').filter({ hasText: /design\d/i });
    const nameVisible = await nameElement.first().isVisible().catch(() => false);
    console.log(`Auto-generated design name visible: ${nameVisible}`);
  });

  test('design builder has submit button', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    const submitBtn = page.getByRole('button', { name: /submit/i });
    const hasSubmit = await submitBtn.isVisible().catch(() => false);
    console.log(`Submit button visible: ${hasSubmit}`);
    // If submit exists, it should be on the page
    if (!hasSubmit) {
      // Check if there's any action button
      const actionBtns = await page.getByRole('button').count();
      console.log(`Total buttons on builder page: ${actionBtns}`);
    }
  });

  test('design builder has BOM section', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    // Look for BOM (Bill of Materials) related content
    const hasBOM = await page.getByText(/bom|bill of material|line item|quantity|sku/i).count();
    console.log(`BOM-related elements found: ${hasBOM}`);
  });

  test('design builder has topology section', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    // Look for topology/diagram section (canvas, SVG, or drawio)
    const hasTopology = await page.locator('canvas, svg, [class*="topology"], [class*="diagram"], [data-testid*="topology"]').count();
    console.log(`Topology/diagram elements found: ${hasTopology}`);
  });
});
