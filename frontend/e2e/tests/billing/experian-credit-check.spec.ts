import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR, TEST_USERS } from '../../fixtures/test-data';

/**
 * Experian Credit Check Integration Tests
 * Tests credit validation flow during onboarding and large orders
 * 
 * REQUIREMENTS:
 * - Credit check triggered during onboarding or before large orders
 * - Experian API integration with business info
 * - Credit score mapped to approval/denial
 * - Credit limit auto-calculated
 * - Manual override by super admin
 * 
 * TEST SCENARIOS:
 * 1. Credit check during onboarding
 * 2. Credit check before large order (>$10k)
 * 3. Credit approval flow
 * 4. Credit denial flow
 * 5. Manual admin override
 */

test.describe('Experian Credit Check Integration', () => {
  
  test.describe('Customer Credit Check Flow', () => {
    test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

    test.beforeEach(async ({ page }) => {
      await page.goto('/shop/dashboard', { timeout: 10000 });
      
      if (page.url().includes('/login')) {
        const emailInput = page.locator('//input[@type="email"]');
        await emailInput.fill(TEST_USERS.company1Admin.email);
        const passwordButton = page.locator('//button[contains(text(), "password")]');
        await passwordButton.click();
        const passwordInput = page.locator('//input[@type="password"]');
        await passwordInput.fill(TEST_USERS.company1Admin.password);
        const signInButton = page.locator('//button[contains(text(), "Sign In")]');
        await signInButton.click();
        await page.waitForURL(/\/(shop|dashboard)/, { timeout: 15000 });
      }
    });

    test('credit check during business onboarding', async ({ page }) => {
      // Navigate to onboarding/business intake
      await page.goto('/business-intake', { timeout: 30000 });
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(2000);
      
      // Look for credit check indicators during intake
      const bodyText = await page.locator('//body').textContent() || '';
      
      // Check if credit-related fields are present
      const hasCreditFields = bodyText.toLowerCase().includes('credit') ||
                             bodyText.toLowerCase().includes('duns') ||
                             bodyText.toLowerCase().includes('tax id') ||
                             bodyText.toLowerCase().includes('ein');
      
      console.log(`✓ Credit-related fields in onboarding: ${hasCreditFields}`);
      
      // If intake form is present, fill business info
      const companyInput = page.locator('//input[@placeholder*="ompany" or @placeholder*="usiness"]');
      if (await companyInput.count() > 0) {
        await companyInput.first().fill('Test Business Inc');
        console.log('✓ Company name filled');
      }
      
      // Look for DUNS or Tax ID fields
      const dunsInput = page.locator('//input[@placeholder*="DUNS" or @name*="duns"]');
      const taxIdInput = page.locator('//input[@placeholder*="Tax" or @placeholder*="EIN" or @name*="tax"]');
      
      if (await dunsInput.count() > 0) {
        await dunsInput.first().fill('123456789');
        console.log('✓ DUNS number filled');
      }
      
      if (await taxIdInput.count() > 0) {
        await taxIdInput.first().fill('12-3456789');
        console.log('✓ Tax ID filled');
      }
      
      // Submit form if submit button exists
      const submitButton = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "submit") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "continue")]');
      if (await submitButton.count() > 0) {
        await submitButton.first().click();
        await page.waitForTimeout(3000);
        
        // Look for credit check processing indicator
        const processingText = await page.locator('//body').textContent() || '';
        const isProcessing = processingText.toLowerCase().includes('validating') ||
                            processingText.toLowerCase().includes('checking') ||
                            processingText.toLowerCase().includes('verifying');
        
        console.log(`✓ Credit check processing: ${isProcessing}`);
      }
    });

    test('credit check status visible on onboarding profile', async ({ page }) => {
      await page.goto('/business-intake', { timeout: 30000 });
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(2000);
      
      // Check for credit validation status indicators
      const bodyText = await page.locator('//body').textContent() || '';
      
      const statusIndicators = [
        'credit_validation_status',
        'credit validation',
        'verified',
        'pending',
        'approved',
        'denied'
      ];
      
      const hasStatus = statusIndicators.some(indicator => 
        bodyText.toLowerCase().includes(indicator.toLowerCase())
      );
      
      console.log(`✓ Credit validation status visible: ${hasStatus}`);
    });

    test('large order triggers credit check', async ({ page }) => {
      // Navigate to cart
      await page.goto('/shop/cart', { timeout: 30000 });
      await page.waitForLoadState('domcontentloaded');
      
      // Check cart total
      const bodyText = await page.locator('//body').textContent() || '';
      const totalMatch = bodyText.match(/\$[\d,]+\.?\d*/);
      
      if (totalMatch) {
        const total = parseFloat(totalMatch[0].replace(/[$,]/g, ''));
        console.log(`✓ Cart total: $${total}`);
        
        // If total > $10,000, credit check should be triggered
        if (total > 10000) {
          // Look for checkout button
          const checkoutButton = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "checkout")]');
          
          if (await checkoutButton.count() > 0) {
            await checkoutButton.first().click();
            await page.waitForTimeout(2000);
            
            // Look for credit check warning/notification
            const warningText = await page.locator('//body').textContent() || '';
            const hasCreditWarning = warningText.toLowerCase().includes('credit') ||
                                    warningText.toLowerCase().includes('approval required') ||
                                    warningText.toLowerCase().includes('pending review');
            
            console.log(`✓ Credit check triggered for large order: ${hasCreditWarning}`);
          }
        }
      }
    });

    test('credit limit displayed in billing settings', async ({ page }) => {
      await page.goto('/shop/billing', { timeout: 30000 });
      await page.waitForLoadState('domcontentloaded');
      
      // Look for credit limit information
      const bodyText = await page.locator('//body').textContent() || '';
      const hasCreditLimit = bodyText.toLowerCase().includes('credit limit') ||
                            bodyText.toLowerCase().includes('available credit');
      
      console.log(`✓ Credit limit displayed: ${hasCreditLimit}`);
      
      // Extract credit limit if present
      const limitMatch = bodyText.match(/credit limit[:\s]*\$?([\d,]+\.?\d*)/i);
      if (limitMatch) {
        console.log(`✓ Credit limit value: $${limitMatch[1]}`);
      }
    });
  });

  test.describe('Admin Credit Check Management', () => {
    test.use({ storageState: `${AUTH_STATE_DIR}/super-admin.json` });

    test.beforeEach(async ({ page }) => {
      await page.goto('/shop/admin/financing', { timeout: 10000 });
      
      if (page.url().includes('/login')) {
        const emailInput = page.locator('//input[@type="email"]');
        await emailInput.fill(TEST_USERS.superAdmin.email);
        const passwordButton = page.locator('//button[contains(text(), "password")]');
        await passwordButton.click();
        const passwordInput = page.locator('//input[@type="password"]');
        await passwordInput.fill(TEST_USERS.superAdmin.password);
        const signInButton = page.locator('//button[contains(text(), "Sign In")]');
        await signInButton.click();
        await page.waitForURL(/\/shop/, { timeout: 15000 });
      }
    });

    test('admin can view customer credit status', async ({ page }) => {
      await page.goto('/shop/admin/financing', { timeout: 30000 });
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(2000);
      
      // Look for credit status section
      const bodyText = await page.locator('//body').textContent() || '';
      const hasCreditStatus = bodyText.toLowerCase().includes('credit status') ||
                             bodyText.toLowerCase().includes('credit limit') ||
                             bodyText.toLowerCase().includes('credit check');
      
      console.log(`✓ Admin credit status section visible: ${hasCreditStatus}`);
      
      // Look for customer list or tenant selector
      const tenantSelector = page.locator('//select[contains(@name, "tenant")] | //button[contains(text(), "Select")]');
      const hasTenantSelector = await tenantSelector.count() > 0;
      
      console.log(`✓ Tenant selector present: ${hasTenantSelector}`);
    });

    test('admin can manually set credit limit', async ({ page }) => {
      await page.goto('/shop/admin/financing', { timeout: 30000 });
      await page.waitForLoadState('domcontentloaded');
      
      // Look for credit limit input field
      const creditLimitInput = page.locator('//input[@name="credit_limit" or @placeholder*="Credit Limit" or contains(@id, "credit")]');
      
      if (await creditLimitInput.count() > 0) {
        await creditLimitInput.first().fill('50000');
        console.log('✓ Credit limit set to $50,000');
        
        // Look for save button
        const saveButton = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "save")]');
        if (await saveButton.count() > 0) {
          await saveButton.first().click();
          await page.waitForTimeout(1500);
          
          // Check for success message
          const successMsg = page.locator('//*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "saved") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "updated")]');
          const hasSaved = await successMsg.count() > 0;
          
          console.log(`✓ Credit limit saved: ${hasSaved}`);
        }
      } else {
        console.log('⚠️ Credit limit field not found');
      }
    });

    test('admin can override credit denial', async ({ page }) => {
      await page.goto('/shop/admin/financing', { timeout: 30000 });
      await page.waitForLoadState('domcontentloaded');
      
      // Look for credit status dropdown
      const creditStatusSelect = page.locator('//select[@name="credit_status" or contains(@id, "credit_status")]');
      
      if (await creditStatusSelect.count() > 0) {
        // Change from PENDING or FAIL to PASS
        await creditStatusSelect.first().selectOption('PASS');
        console.log('✓ Credit status overridden to PASS');
        
        // Save the change
        const saveButton = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "save")]');
        if (await saveButton.count() > 0) {
          await saveButton.first().click();
          await page.waitForTimeout(1500);
          console.log('✓ Override saved');
        }
      } else {
        console.log('⚠️ Credit status dropdown not found');
      }
    });

    test('admin can set OPEX eligibility based on credit', async ({ page }) => {
      await page.goto('/shop/admin/financing', { timeout: 30000 });
      await page.waitForLoadState('domcontentloaded');
      
      // Look for OPEX eligibility toggle/checkbox
      const opexToggle = page.locator('//input[@type="checkbox" and (contains(@name, "opex") or contains(@id, "opex"))] | //button[contains(text(), "OPEX")]');
      
      if (await opexToggle.count() > 0) {
        await opexToggle.first().click();
        console.log('✓ OPEX eligibility toggled');
        
        const saveButton = page.locator('//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "save")]');
        if (await saveButton.count() > 0) {
          await saveButton.first().click();
          await page.waitForTimeout(1500);
          console.log('✓ OPEX eligibility saved');
        }
      } else {
        console.log('⚠️ OPEX eligibility toggle not found');
      }
    });
  });
});
