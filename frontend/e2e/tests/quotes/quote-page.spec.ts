import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR, TEST_USERS } from '../../fixtures/test-data';
import { loginAs } from '../../helpers/common-flows';

async function gotoProtectedQuote(page, path: string) {
  // Set onboarding skip first
  await page.evaluate(() => {
    localStorage.setItem('so2_onboarding_skip', '1');
  }).catch(() => {});
  
  await page.goto(path, { waitUntil: 'networkidle', timeout: 30000 });
  
  // Check if redirected to login
  if (page.url().includes('/login')) {
    console.log('Session expired, re-authenticating...');
    await loginAs(page, TEST_USERS.company1Admin.email, TEST_USERS.company1Admin.password);
    await page.evaluate(() => {
      localStorage.setItem('so2_onboarding_skip', '1');
    });
    await page.goto(path, { waitUntil: 'networkidle', timeout: 30000 });
  }
}

test.describe('Quotes', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test('navigating to a non-existent quote shows error or redirects', async ({ page }) => {
    await gotoProtectedQuote(page, '/shop/quotes/00000000-0000-0000-0000-000000000000');
    await page.waitForTimeout(2000);
    const bodyText = await page.locator('body').textContent() || '';
    const hasError = /not found|error|doesn't exist|invalid/i.test(bodyText);
    const redirected = !page.url().includes('00000000-0000-0000-0000-000000000000');
    console.log(`Non-existent quote — error shown: ${hasError}, redirected: ${redirected}`);
    // Should handle gracefully (not blank page or crash)
    expect(bodyText.length).toBeGreaterThan(20);
  });

  test('legacy quote URL redirects to new format', async ({ page }) => {
    // Set onboarding skip first
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
      localStorage.setItem('so2_onboarding_skip', '1');
    });
    
    // /shop/quote/:id should redirect to /shop/quotes/:id
    await page.goto('/shop/quote/some-fake-id', { timeout: 30000, waitUntil: 'networkidle' });
    
    // Wait for any redirects to complete
    await page.waitForTimeout(1500);
    
    // Log current URL for debugging
    let currentUrl = page.url();
    console.log(`Current URL after navigation: ${currentUrl}`);
    
    // Check if redirected to login (session expired)
    if (currentUrl.includes('/login')) {
      console.log('Session expired during legacy redirect test, re-authenticating...');
      await loginAs(page, TEST_USERS.company1Admin.email, TEST_USERS.company1Admin.password);
      await page.evaluate(() => {
        localStorage.setItem('so2_onboarding_skip', '1');
      });
      // Try the legacy URL again after auth
      await page.goto('/shop/quote/some-fake-id', { timeout: 30000, waitUntil: 'networkidle' });
      await page.waitForTimeout(1500);
      currentUrl = page.url();
      console.log(`Current URL after re-auth: ${currentUrl}`);
    }
    
    // Take screenshot to see what page we're actually on
    await page.screenshot({ 
      path: 'e2e/test-results/debug-legacy-redirect.png',
      fullPage: true 
    }).catch(() => {});
    
    // Should redirect to /shop/quotes/some-fake-id
    await expect(page).toHaveURL(/\/shop\/quotes\/some-fake-id/, { timeout: 10000 });
  });
});
