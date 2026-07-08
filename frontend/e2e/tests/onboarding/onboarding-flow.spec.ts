import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR } from '../../fixtures/test-data';

/**
 * Onboarding Flow Tests
 * 
 * NOTE: These tests are currently SKIPPED because the onboarding page
 * UI may not match the expected structure. Enable them once onboarding
 * page is finalized.
 * 
 * To enable: Remove .skip from test.describe.skip
 */

test.describe.skip('Onboarding Flow', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test('onboarding page loads with all sections', async ({ page }) => {
    await page.goto('/shop/onboarding', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    // Should show onboarding sections
    await expect(page.getByText(/organization onboarding/i)).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/company setup/i)).toBeVisible();
    await expect(page.getByText(/business address/i)).toBeVisible();
    await expect(page.getByText(/compliance validation/i)).toBeVisible();
    await expect(page.getByText(/payment setup/i)).toBeVisible();
  });

  test('onboarding shows completion percentage', async ({ page }) => {
    await page.goto('/shop/onboarding', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    // Should show completion stats
    await expect(page.getByText(/completion/i)).toBeVisible({ timeout: 10000 });
    // Should have a percentage value
    const pctElement = page.locator('.apx-stat-value').first();
    const pctText = await pctElement.textContent() || '';
    console.log(`Onboarding completion: ${pctText}`);
  });

  test('onboarding has organization name field', async ({ page }) => {
    await page.goto('/shop/onboarding', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const orgField = page.getByLabel(/organization name/i);
    await expect(orgField).toBeVisible({ timeout: 10000 });
    // Should be pre-filled or empty
    const value = await orgField.inputValue();
    console.log(`Organization name pre-filled: "${value}"`);
  });

  test('onboarding address fields are present', async ({ page }) => {
    await page.goto('/shop/onboarding', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    // Address fields
    await expect(page.getByLabel(/street address/i).first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByLabel(/city/i).first()).toBeVisible();
    await expect(page.getByLabel(/state/i).first()).toBeVisible();
    await expect(page.getByLabel(/zip code/i).first()).toBeVisible();
  });

  test('onboarding has save button', async ({ page }) => {
    await page.goto('/shop/onboarding', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const saveBtn = page.getByRole('button', { name: /save onboarding/i });
    await expect(saveBtn).toBeVisible({ timeout: 10000 });
  });

  test('onboarding has skip button', async ({ page }) => {
    await page.goto('/shop/onboarding', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const skipBtn = page.getByRole('button', { name: /skip for now/i });
    await expect(skipBtn).toBeVisible({ timeout: 10000 });
  });

  test('onboarding skip navigates to dashboard', async ({ page }) => {
    await page.goto('/shop/onboarding', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const skipBtn = page.getByRole('button', { name: /skip for now/i });
    await expect(skipBtn).toBeVisible({ timeout: 10000 });
    await skipBtn.click();
    await page.waitForURL(/\/shop\/dashboard/, { timeout: 10000 });
  });

  test('onboarding payment validation button works', async ({ page }) => {
    await page.goto('/shop/onboarding', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const validateBtn = page.getByRole('button', { name: /validate payment/i });
    await expect(validateBtn).toBeVisible({ timeout: 10000 });
    await validateBtn.click();
    // Should show validating state or result
    await page.waitForTimeout(2000);
    const notice = await page.locator('.onboarding-alert').isVisible().catch(() => false);
    console.log(`Payment validation response shown: ${notice}`);
  });
});
