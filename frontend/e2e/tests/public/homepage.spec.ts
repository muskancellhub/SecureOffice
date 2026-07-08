import { test, expect } from '../../fixtures/evidence-fixture';

test.describe('Public pages — no auth required', () => {
  test('homepage loads successfully', async ({ page }) => {
    await page.goto('/', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).not.toBeEmpty();
  });

  test('homepage has navigation to login', async ({ page }) => {
    await page.goto('/', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    const loginLink = page.getByRole('link', { name: /log\s*in|sign\s*in|get started/i });
    await expect(loginLink).toBeVisible({ timeout: 10000 });
  });

  test('business intake page loads', async ({ page }) => {
    await page.goto('/business-intake', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).not.toBeEmpty();
  });

  test('login page loads with email field', async ({ page }) => {
    await page.goto('/login', { timeout: 30000 });
    await expect(page.getByPlaceholder('Email Address')).toBeVisible({ timeout: 10000 });
  });

  test('signup page loads', async ({ page }) => {
    await page.goto('/signup', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).not.toBeEmpty();
  });
});
