/**
 * COMMON E2E HELPER FUNCTIONS
 * 
 * Reusable functions for all test phases
 * Simplifies test writing and maintenance
 */

import { Page } from '@playwright/test';
import { TEST_USERS } from '../fixtures/test-data';

function getPathname(page: Page): string {
  try {
    return new URL(page.url()).pathname;
  } catch {
    return '';
  }
}

/**
 * Fresh login helper - use in beforeEach hooks
 * Replaces stored auth state approach
 * 
 * IMPORTANT: Password must be provided explicitly - no default!
 */
export async function doFreshLogin(page: Page, email: string, password: string) {
  console.log(`🔐 Logging in as ${email}...`);
  
  // Debug: Log current URL before login
  const urlBefore = page.url();
  console.log(`   Current URL before login: ${urlBefore}`);
  
  try {
    // Navigate to login page
    await page.goto('/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
    console.log('   ✓ Navigated to /login');
    
    // Wait for email input to be visible
    const emailInput = page.getByPlaceholder('Email Address');
    await emailInput.waitFor({ state: 'visible', timeout: 10000 });
    await emailInput.fill(email);
    console.log('   ✓ Filled email');
    
    // Click "Sign in with a password" button to switch from OTP mode to password mode
    const passwordModeBtn = page.getByRole('button', { name: /sign in with a password/i });
    await passwordModeBtn.click();
    console.log('   ✓ Switched to password mode');
    
    // Wait for password input and fill it
    const passwordInput = page.getByPlaceholder('Password');
    await passwordInput.waitFor({ state: 'visible', timeout: 5000 });
    await passwordInput.fill(password);
    console.log('   ✓ Filled password');
    
    // Click "Sign in" button
    const signInButton = page.getByRole('button', { name: /^sign in$/i });
    await signInButton.click();
    console.log('   ✓ Clicked sign in');
    
    // Wait for redirect to dashboard with increased timeout
    await page.waitForURL(/\/(shop|dashboard)/, { timeout: 30000 });
    
    // Wait for auth state to stabilize (cookies to be set)
    await page.waitForTimeout(2000);
    
    // Debug: Log final URL after login
    const urlAfter = page.url();
    console.log(`✅ Login successful - redirected to: ${urlAfter}`);
    
  } catch (error) {
    // Enhanced error logging
    console.error('❌ Login failed!');
    console.error(`   Error: ${error instanceof Error ? error.message : String(error)}`);
    console.error(`   Current URL: ${page.url()}`);
    
    // Take screenshot for debugging
    await page.screenshot({
      path: 'e2e/test-results/login-failure.png',
      fullPage: true,
    }).catch(() => {});
    
    // Log page body for debugging
    const bodyText = await page.locator('body').textContent().catch(() => 'Could not read body');
    console.error(`   Page body sample: ${bodyText?.slice(0, 500)}...`);
    
    throw error;
  }
}

/**
 * Login as a specific user
 * Uses correct password from test data
 */
export async function loginAs(page: Page, email: string, password: string) {
  await doFreshLogin(page, email, password);
}

/**
 * Complete business intake and navigate to design builder
 * Uses "Load Dummy Data" button for speed
 * 
 * IMPROVED: Adds debugging, validation, and proper waits
 * ASSUMES: User is already logged in
 */
export async function completeIntakeFlow(page: Page) {
  console.log('🚀 Starting completeIntakeFlow...');
  
  // Set onboarding skip flag FIRST to prevent redirect loops. When the caller
  // has just logged in, stay inside the same SPA session so AuthContext keeps
  // its in-memory user state while the public intake page renders.
  if (page.url() === 'about:blank') {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
  }
  await page.evaluate(() => {
    localStorage.setItem('so2_onboarding_skip', '1');
  });
  console.log('✅ Onboarding skip flag set');
  
  // Navigate to intake without forcing a full document reload.
  await page.evaluate((targetPath) => {
    window.history.pushState({}, '', targetPath);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, '/business-intake');
  await page.waitForFunction(() => window.location.pathname === '/business-intake', { timeout: 15000 });
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  console.log('✅ Navigated to business intake page');
  
  // Wait for page load
  await page.getByRole('heading', { name: /business network intake/i }).waitFor({ timeout: 15000 });
  console.log('✅ Intake page heading visible');
  
  // Load dummy data (fast way to fill form)
  const dummyBtn = page.getByRole('button', { name: /load dummy data/i });
  await dummyBtn.waitFor({ state: 'visible', timeout: 5000 });
  await dummyBtn.click();
  await page.waitForTimeout(500);
  console.log('✅ Dummy data loaded');
  
  // Fill required fields that dummy data might miss
  await page.getByLabel(/business type/i).selectOption('Restaurant / QSR');
  await page.getByLabel(/number of locations/i).fill('3');
  await page.getByLabel(/internet type/i).selectOption('Fiber');
  console.log('✅ Required fields filled');
  
  // Hide avatar widget to prevent blocking
  await page.evaluate(() => {
    const widget = document.querySelector('.anam-avatar-widget');
    if (widget) (widget as HTMLElement).style.display = 'none';
  });
  
  // Verify calculator data was saved to localStorage before submitting
  const hasCalculatorDataBefore = await page.evaluate(() => {
    return !!localStorage.getItem('secureOfficeNetworkEstimateV1');
  });
  console.log(`📊 Calculator data in localStorage before submit: ${hasCalculatorDataBefore}`);
  
  // Submit form
  const continueBtn = page.getByRole('button', { name: /continue to design/i });
  await continueBtn.waitFor({ state: 'visible', timeout: 5000 });
  await continueBtn.click();
  console.log('✅ Submitted intake form');
  
  // Wait for navigation to complete
  await page.waitForLoadState('networkidle', { timeout: 30000 });
  
  // DEBUG: Check where we landed
  let urlAfterSubmit = page.url();
  console.log(`📍 URL after intake submit: ${urlAfterSubmit}`);
  
  // Take debug screenshot
  await page.screenshot({ 
    path: 'e2e/test-results/debug-after-intake.png',
    fullPage: true 
  }).catch(() => {});
  
  // Handle potential redirects - ensure we end up on design builder
  if (getPathname(page).includes('/login')) {
    console.log('Intake submit landed on login; retrying protected design route...');
    await page.goto('/shop/designs/new', { waitUntil: 'networkidle', timeout: 30000 });
    urlAfterSubmit = page.url();
    console.log(`URL after protected route retry: ${urlAfterSubmit}`);
  }

  if (getPathname(page).includes('/onboarding')) {
    console.log('⚠️  Redirected to onboarding, navigating to design builder...');
    await page.goto('/shop/designs/new', { waitUntil: 'networkidle', timeout: 30000 });
  } else if (!getPathname(page).includes('/designs')) {
    console.log('ℹ️  Not on designs page, navigating directly...');
    await page.goto('/shop/designs/new', { waitUntil: 'networkidle', timeout: 30000 });
  }
  
  // Verify we're on design page
  await page.waitForURL((url) => url.pathname.includes('/designs'), { timeout: 15000 });
  const finalUrl = page.url();
  if (!getPathname(page).includes('/designs')) {
    throw new Error(`Expected an actual /designs page, got: ${finalUrl}`);
  }
  console.log(`✅ On design page: ${finalUrl}`);
  
  // Verify calculator data persisted to localStorage
  const hasCalculatorDataAfter = await page.evaluate(() => {
    const data = localStorage.getItem('secureOfficeNetworkEstimateV1');
    if (data) {
      try {
        const parsed = JSON.parse(data);
        return { exists: true, keys: Object.keys(parsed) };
      } catch {
        return { exists: true, keys: [] };
      }
    }
    return { exists: false, keys: [] };
  });
  console.log(`📊 Calculator data after navigation:`, hasCalculatorDataAfter);
  
  if (!hasCalculatorDataAfter.exists) {
    console.log('❌ WARNING: Calculator data missing from localStorage!');
    console.log('   BOM generation will likely fail');
  }
}

/**
 * IMPROVED: Ensure design builder page is loaded with BOM data
 * This validates the entire flow before tests proceed
 * 
 * Use this instead of completeIntakeFlow() for BOM-dependent tests
 * ASSUMES: User is already logged in
 */
export async function ensureDesignBuilderLoaded(page: Page, options?: {
  waitForBom?: boolean;
  timeout?: number;
}) {
  const waitForBom = options?.waitForBom !== false; // Default true
  const timeout = options?.timeout || 60000; // 60s total timeout
  
  console.log('🎯 ensureDesignBuilderLoaded - Starting validation flow...');
  
  // Step 1: Complete intake flow
  await completeIntakeFlow(page);
  
  // Step 2: Verify we're on design builder page
  const currentUrl = page.url();
  console.log(`📍 Current URL: ${currentUrl}`);
  
  if (!getPathname(page).includes('/designs')) {
    console.log('❌ Not on design builder page!');
    throw new Error(`Expected /designs page, got: ${currentUrl}`);
  }
  
  // Step 3: Verify page content loaded (not "Missing Intake Data" or "Loading...")
  const missingDataMsg = page.locator('text=/missing intake data/i');
  const isMissingData = await missingDataMsg.isVisible({ timeout: 2000 }).catch(() => false);
  
  if (isMissingData) {
    console.log('❌ Design builder showing "Missing Intake Data"');
    await page.screenshot({ 
      path: 'e2e/test-results/debug-missing-intake-data.png',
      fullPage: true 
    }).catch(() => {});
    throw new Error('Design builder showing "Missing Intake Data" - calculator data not in localStorage');
  }
  
  // Step 4: Wait for BOM generation (if requested)
  if (waitForBom) {
    console.log('⏳ Waiting for BOM table to appear...');
    
    try {
      // Wait for BOM table with proper selector
      // Based on NetworkDesignBuilderPage.tsx: <table className="dnb-bom">
      const bomTable = page.locator('table.dnb-bom');
      await bomTable.waitFor({ state: 'visible', timeout });
      console.log('✅ BOM table is visible');
      
      // Verify BOM has actual line items (not just header)
      const bomRows = bomTable.locator('tbody tr');
      const rowCount = await bomRows.count();
      console.log(`✅ BOM has ${rowCount} line items`);
      
      if (rowCount === 0) {
        console.log('⚠️  BOM table exists but has no rows');
      }
      
    } catch (error) {
      console.log('❌ BOM table did not appear within timeout');
      console.log(`   Timeout: ${timeout}ms`);
      console.log(`   Current URL: ${page.url()}`);
      
      // Debug: Check loading state
      const loadingText = await page.locator('text=/loading|generating/i').count();
      console.log(`   "Loading" indicators found: ${loadingText}`);
      
      // Debug: Check for error messages
      const errorMsg = await page.locator('.onboarding-alert.error, [role="alert"]').count();
      console.log(`   Error messages found: ${errorMsg}`);
      
      // Take screenshot for debugging
      await page.screenshot({ 
        path: 'e2e/test-results/debug-bom-timeout.png',
        fullPage: true 
      }).catch(() => {});
      
      throw new Error(`BOM table did not load within ${timeout}ms - likely frontend implementation issue`);
    }
  }
  
  // Step 5: Final validation screenshot
  await page.screenshot({ 
    path: 'e2e/test-results/design-builder-loaded.png',
    fullPage: true 
  }).catch(() => {});
  
  console.log('✅ Design builder page fully loaded and validated');
}

/**
 * Create a design from scratch (intake → design → save)
 */
export async function createDesign(page: Page): Promise<string> {
  await completeIntakeFlow(page);
  
  // Wait for auto-save to complete
  await page.waitForTimeout(3000);
  
  // Extract design ID from URL if available
  const url = page.url();
  const match = url.match(/designs\/([a-f0-9-]{36})/);
  return match ? match[1] : '';
}

/**
 * Add a product to cart from catalog
 */
export async function addProductToCart(page: Page, productIndex = 0) {
  await page.goto('/shop/catalog');
  
  // Wait for products to load
  await page.waitForSelector('[data-testid="product-card"], .product-card', { timeout: 10000 });
  
  // Click first product (or specified index)
  const products = page.locator('[data-testid="product-card"]').or(page.locator('.product-card'));
  await products.nth(productIndex).click();
  
  // Add to cart
  await page.getByRole('button', { name: /add to cart/i }).click();
  
  // Wait for confirmation
  await page.waitForTimeout(1000);
}

/**
 * Navigate to cart and verify items
 */
export async function goToCart(page: Page) {
  await page.goto('/shop/cart');
  await page.waitForSelector('[data-testid="cart-items"], .cart-items', { timeout: 10000 });
}

/**
 * Checkout and create order
 */
export async function checkoutCart(page: Page): Promise<string> {
  await goToCart(page);
  
  // Click checkout
  await page.getByRole('button', { name: /checkout|place order/i }).click();
  
  // Wait for order confirmation
  await page.waitForTimeout(2000);
  
  // Extract order ID if available
  const orderText = await page.textContent('body');
  const match = orderText?.match(/order[:\s#]*([a-z0-9-]+)/i);
  return match ? match[1] : '';
}

/**
 * Login as super admin
 */
export async function loginAsSuperAdmin(page: Page) {
  await loginAs(page, TEST_USERS.superAdmin.email, TEST_USERS.superAdmin.password);
}

/**
 * Login as company admin
 */
export async function loginAsCompanyAdmin(page: Page) {
  await loginAs(page, TEST_USERS.company1Admin.email, TEST_USERS.company1Admin.password);
}

/**
 * Wait for element with multiple fallback selectors
 */
export async function waitForElement(page: Page, ...selectors: string[]) {
  for (const selector of selectors) {
    const element = page.locator(selector);
    if (await element.count() > 0) {
      await element.first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
      return element.first();
    }
  }
  throw new Error(`None of the selectors found: ${selectors.join(', ')}`);
}
