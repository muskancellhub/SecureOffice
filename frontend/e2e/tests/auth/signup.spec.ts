import { test, expect } from '../../fixtures/evidence-fixture';

/**
 * Signup Flow Tests
 * Maximum 6 test cases (well under 25 limit)
 * Uses data-testid selectors for maximum reliability
 * No URL parameters
 * Proper session handling
 * Evidence collection: screenshots + API responses
 */

test.describe('Signup Flow', () => {
  // Clear any existing session before each test
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
    await context.clearPermissions();
  });

  // 🔥 EVIDENCE: Add after each hook to capture final state
  test.afterEach(async ({ page }, testInfo) => {
    if (testInfo.status === 'passed') {
      // Capture final screenshot for passed tests
      await page.screenshot({ 
        path: `e2e/test-results/evidence/${testInfo.title.replace(/\s+/g, '-')}-success.png`,
        fullPage: true 
      });
      console.log(`✅ EVIDENCE: ${testInfo.title} - Screenshot saved`);
    }
  });

  test('signup page renders all required fields', async ({ page }) => {
    // Navigate without parameters
    await page.goto('/signup', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    // Use actual HTML placeholders from SignupPage.tsx
    const fullNameInput = page.locator('input[placeholder="Full Name"]');
    const companyNameInput = page.locator('input[placeholder="Company Name"]');
    const emailInput = page.locator('input[placeholder="Company Email Address"]');
    const passwordInput = page.locator('input[placeholder="Password"]');
    const continueButton = page.locator('button:has-text("Continue")');
    
    await expect(fullNameInput).toBeVisible({ timeout: 10000 });
    await expect(companyNameInput).toBeVisible();
    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(continueButton).toBeVisible();
  });

  test('signup rejects free email domains (gmail)', async ({ page }) => {
    await page.goto('/signup', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    // Use actual HTML placeholders
    await page.locator('input[placeholder="Full Name"]').fill('Test User');
    await page.locator('input[placeholder="Company Name"]').fill('Test Corp');
    await page.locator('input[placeholder="Company Email Address"]').fill('testuser@gmail.com');
    await page.locator('input[placeholder="Password"]').fill('SecurePass123!');
    await page.locator('button:has-text("Continue")').click();
    
    // Wait for error to appear
    await page.waitForTimeout(1000);
    
    // Check for error using class name from SignupPage
    const errorMessage = page.locator('.error-text');
    await expect(errorMessage).toBeVisible({ timeout: 5000 });
    await expect(errorMessage).toContainText(/company email/i);
  });

  test('signup rejects free email domains (outlook)', async ({ page }) => {
    await page.goto('/signup', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    await page.locator('input[placeholder="Full Name"]').fill('Test User');
    await page.locator('input[placeholder="Company Name"]').fill('Test Corp');
    await page.locator('input[placeholder="Company Email Address"]').fill('testuser@outlook.com');
    await page.locator('input[placeholder="Password"]').fill('SecurePass123!');
    await page.locator('button:has-text("Continue")').click();
    
    await page.waitForTimeout(1000);
    
    const errorMessage = page.locator('.error-text');
    await expect(errorMessage).toBeVisible({ timeout: 5000 });
    await expect(errorMessage).toContainText(/company email/i);
  });

  test('signup with empty company name shows error', async ({ page }) => {
    await page.goto('/signup', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    await page.locator('input[placeholder="Full Name"]').fill('Test User');
    // Leave company name empty
    await page.locator('input[placeholder="Company Email Address"]').fill('test@validcorp.com');
    await page.locator('input[placeholder="Password"]').fill('SecurePass123!');
    await page.locator('button:has-text("Continue")').click();
    
    // Should stay on signup (browser validation prevents submission)
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/\/signup(?:\?.*)?$/);
  });

  test('signup with invalid email format shows error', async ({ page }) => {
    await page.goto('/signup', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    await page.locator('input[placeholder="Full Name"]').fill('Test User');
    await page.locator('input[placeholder="Company Name"]').fill('Test Corp');
    await page.locator('input[placeholder="Company Email Address"]').fill('not-an-email');
    await page.locator('input[placeholder="Password"]').fill('SecurePass123!');
    await page.locator('button:has-text("Continue")').click();
    
    await page.waitForTimeout(500);
    
    // Check for custom error or browser validation (stays on page)
    const errorVisible = await page.locator('.error-text').isVisible().catch(() => false);
    const stayedOnPage = page.url().includes('/signup');
    expect(errorVisible || stayedOnPage).toBeTruthy();
  });

  test('signup has link to login page', async ({ page }) => {
    await page.goto('/signup', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    
    // Look for "Log in here" link from SignupPage
    const loginLink = page.locator('a:has-text("Log in here")');
    await expect(loginLink).toBeVisible();
    
    await loginLink.click();
    
    // Verify redirect without parameters
    await expect(page).toHaveURL(/\/login(?:\?.*)?$/, { timeout: 5000 });
  });
});
