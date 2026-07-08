import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR } from '../../fixtures/test-data';

/**
 * Logout Tests
 * Maximum 2 test cases (well under 25 limit)
 * Uses XPath selectors for robustness
 * No URL parameters
 * Proper session handling with storage state
 */

test.describe('Logout', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test('logout clears session and redirects', async ({ page }) => {
    // Navigate to shop page (no parameters)
    await page.goto('/shop');
    
    // Wait for page to load completely
    await page.waitForLoadState('networkidle');

    // Verify we're on the shop page (authenticated)
    if (page.url().includes('/shop')) {
      // Use XPath to find user menu or logout button
      const userMenu = page.locator('//div[@data-testid="user-menu"] | //div[contains(@class, "user-menu")] | //button[contains(@class, "avatar")] | //div[contains(@class, "profile")]').first();
      const logoutBtn = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "log out") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "sign out")]');

      // Try to open user menu first if it exists
      const isMenuVisible = await userMenu.isVisible({ timeout: 3000 }).catch(() => false);
      if (isMenuVisible) {
        await userMenu.click();
        await logoutBtn.click({ timeout: 5000 });
      } else {
        // Direct logout button might be visible
        const isLogoutVisible = await logoutBtn.isVisible({ timeout: 3000 }).catch(() => false);
        if (isLogoutVisible) {
          await logoutBtn.click();
        }
      }

      // After logout, should redirect to login or home (no parameters in URL)
      await page.waitForURL(/\/(login)?(?:\?.*)?$/, { timeout: 10000 });
      
      // Verify session is cleared by checking cookies
      const cookies = await page.context().cookies();
      const authCookies = cookies.filter(c => c.name.includes('auth') || c.name.includes('session') || c.name.includes('token'));
      expect(authCookies.length).toBe(0);
    }
  });

  test('protected route not accessible after logout', async ({ page }) => {
    // Explicitly clear all session data
    await page.context().clearCookies();
    await page.context().clearPermissions();
    
    // Try to access protected route directly (no parameters)
    await page.goto('/shop/designs');
    
    // Should redirect to login page
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/, { timeout: 10000 });
    
    // Verify we can see login page elements using XPath
    const loginElement = page.locator('//input[@type="email" or @placeholder="Email Address"]');
    await expect(loginElement).toBeVisible({ timeout: 5000 });
  });
});
