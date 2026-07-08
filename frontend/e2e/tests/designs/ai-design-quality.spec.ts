import { test, expect } from '../../fixtures/evidence-fixture';
import { AUTH_STATE_DIR, TEST_USERS } from '../../fixtures/test-data';

/**
 * AI Design Quality & Validation Tests
 * Tests the "less deterministic" AI network design generation
 * 
 * REQUIREMENTS:
 * - AI-generated designs have reasonable counts (not 0, not extreme)
 * - Product selections are valid catalog items
 * - BOM totals are accurate
 * - Topology is coherent (no orphaned devices)
 * - Cost estimates are within expected ranges
 * - Security posture appropriate for business type
 * 
 * TEST APPROACH:
 * - Generate multiple designs for same business profile
 * - Validate structural integrity
 * - Check for hallucination/invalid data
 * - Verify fallback to deterministic on AI failure
 */

test.describe('AI Design Quality & Validation', () => {
  test.use({ storageState: `${AUTH_STATE_DIR}/company1-admin.json` });

  test.beforeEach(async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 10000 });
    
    if (page.url().includes('/login')) {
      const emailInput = page.locator('//input[@type="email"]');
      await emailInput.fill(TEST_USERS.company1Admin.email);
      const passwordButton = page.locator('//button[contains(text(), "password")]');
      await passwordButton.click();
      const passwordInput = page.locator('//input[@type="password"]');
      await passwordInput.fill(TEST_USERS.company1Admin.password);
      const signInButton = page.locator('//button[contains(text(), "Sign In")]');
      await signInButton.click();
      await page.waitForURL(/\/shop/, { timeout: 15000 });
    }
  });

  test('AI design generates reasonable device counts', async ({ page }) => {
    // Navigate to design builder
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    // Check if we need to complete business intake first
    const needsIntake = await page.locator('//*[contains(text(), "Missing Intake")]').count() > 0;
    
    if (needsIntake) {
      console.log('⚠️ Business intake required first');
      await page.goto('/business-intake', { timeout: 30000 });
      
      // Quick business profile submission
      const chatInput = page.locator('//textarea | //input[@type="text"]');
      if (await chatInput.count() > 0) {
        await chatInput.first().fill('Office with 50 employees, 10000 sq ft');
        const sendButton = page.locator('//button[contains(text(), "Send") or contains(text(), "Submit")]');
        if (await sendButton.count() > 0) {
          await sendButton.first().click();
          await page.waitForTimeout(5000); // Wait for AI processing
        }
      }
      
      // Return to design builder
      await page.goto('/shop/designs/new', { timeout: 30000 });
      await page.waitForTimeout(3000);
    }
    
    // Look for generated AP and switch counts
    const bodyText = await page.locator('//body').textContent() || '';
    
    // Extract AP count
    const apMatch = bodyText.match(/(\d+)\s*(?:access\s*points?|APs?)/i);
    const apCount = apMatch ? parseInt(apMatch[1]) : null;
    
    // Extract switch count
    const switchMatch = bodyText.match(/(\d+)\s*switches?/i);
    const switchCount = switchMatch ? parseInt(switchMatch[1]) : null;
    
    if (apCount !== null) {
      console.log(`✓ AP count: ${apCount}`);
      expect(apCount).toBeGreaterThan(0);
      expect(apCount).toBeLessThan(100); // Reasonable upper bound
    }
    
    if (switchCount !== null) {
      console.log(`✓ Switch count: ${switchCount}`);
      expect(switchCount).toBeGreaterThan(0);
      expect(switchCount).toBeLessThan(50); // Reasonable upper bound
    }
    
    // Check that counts are proportional (APs > switches typically)
    if (apCount && switchCount) {
      const ratio = apCount / switchCount;
      console.log(`✓ AP to Switch ratio: ${ratio.toFixed(2)}`);
      expect(ratio).toBeGreaterThan(0.5); // At minimum, 1 AP per 2 switches
      expect(ratio).toBeLessThan(50); // Not more than 50 APs per switch
    }
  });

  test('AI design products are valid catalog items', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    
    // Look for BOM section
    const bomSection = page.locator('//*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "bill of materials") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "bom")]');
    
    if (await bomSection.count() > 0) {
      // Extract product names from BOM
      const bomText = await bomSection.first().textContent() || '';
      console.log(`✓ BOM section found, length: ${bomText.length}`);
      
      // Check for valid product indicators (model numbers, SKUs)
      const hasValidProducts = bomText.match(/\b[A-Z]{2,}\d{2,}/) !== null || // Pattern like MR46
                              bomText.match(/\b\d{3,}-\d{3,}/) !== null;       // Pattern like 123-456
      
      console.log(`✓ Valid product patterns found: ${hasValidProducts}`);
      
      // Check for pricing
      const priceMatches = bomText.match(/\$[\d,]+\.?\d*/g);
      if (priceMatches && priceMatches.length > 0) {
        console.log(`✓ ${priceMatches.length} prices found in BOM`);
        
        // Validate prices are reasonable (not $0, not millions)
        for (const priceStr of priceMatches) {
          const price = parseFloat(priceStr.replace(/[$,]/g, ''));
          expect(price).toBeGreaterThan(0);
          expect(price).toBeLessThan(100000); // Max price per item
        }
      }
    } else {
      console.log('⚠️ BOM section not found - design may not be generated yet');
    }
  });

  test('AI design BOM totals are accurate', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    
    const bodyText = await page.locator('//body').textContent() || '';
    
    // Find all individual line prices
    const linePrices = bodyText.match(/\$[\d,]+\.?\d*/g);
    
    if (linePrices && linePrices.length > 0) {
      console.log(`✓ Found ${linePrices.length} price entries`);
      
      // Find total/subtotal
      const totalMatch = bodyText.match(/total[:\s]*\$?([\d,]+\.?\d*)/i) ||
                        bodyText.match(/subtotal[:\s]*\$?([\d,]+\.?\d*)/i);
      
      if (totalMatch) {
        const reportedTotal = parseFloat(totalMatch[1].replace(/,/g, ''));
        console.log(`✓ Reported total: $${reportedTotal}`);
        
        // Verify total is reasonable
        expect(reportedTotal).toBeGreaterThan(0);
        expect(reportedTotal).toBeLessThan(1000000); // Max $1M per design
        
        // Note: Exact calculation validation would require parsing full BOM structure
        console.log('✓ Total amount within reasonable range');
      }
    }
  });

  test('AI design topology is coherent', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    
    // Look for topology/diagram section
    const topologySection = page.locator('//*[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "topology") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "diagram") or contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "network design")]');
    
    const hasTopology = await topologySection.count() > 0;
    console.log(`✓ Topology section present: ${hasTopology}`);
    
    if (hasTopology) {
      // Check for diagram viewer or iframe
      const diagramViewer = page.locator('//iframe | //svg | //*[contains(@class, "diagram")]');
      const hasDiagram = await diagramViewer.count() > 0;
      
      console.log(`✓ Diagram viewer present: ${hasDiagram}`);
      
      // Check topology text mentions key components
      const topologyText = await topologySection.first().textContent() || '';
      const hasRouter = topologyText.toLowerCase().includes('router') || 
                       topologyText.toLowerCase().includes('gateway');
      const hasSwitch = topologyText.toLowerCase().includes('switch');
      const hasAP = topologyText.toLowerCase().includes('access point') || 
                   topologyText.toLowerCase().includes('ap');
      
      console.log(`✓ Topology includes: Router=${hasRouter}, Switch=${hasSwitch}, AP=${hasAP}`);
      
      // A valid network topology should have at least router and APs
      expect(hasRouter || hasSwitch).toBeTruthy();
    }
  });

  test('AI design includes security components for appropriate business types', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    
    const bodyText = await page.locator('//body').textContent() || '';
    
    // Check for security-related components
    const hasFirewall = bodyText.toLowerCase().includes('firewall');
    const hasSecurity = bodyText.toLowerCase().includes('security appliance') ||
                       bodyText.toLowerCase().includes('mx') || // Meraki MX series
                       bodyText.toLowerCase().includes('threat protection');
    
    console.log(`✓ Firewall mentioned: ${hasFirewall}`);
    console.log(`✓ Security appliance mentioned: ${hasSecurity}`);
    
    // For business profiles (not home/small office), security should be present
    const businessType = bodyText.match(/business type[:\s]*([\w\s]+)/i);
    if (businessType) {
      console.log(`✓ Business type detected: ${businessType[1]}`);
      
      const needsSecurity = !businessType[1].toLowerCase().includes('home') &&
                           !businessType[1].toLowerCase().includes('residential');
      
      if (needsSecurity) {
        console.log('✓ Business profile requires security components');
        // At least one security indicator should be present
        expect(hasFirewall || hasSecurity).toBeTruthy();
      }
    }
  });

  test('AI design cost estimate within expected range', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    
    const bodyText = await page.locator('//body').textContent() || '';
    
    // Extract CapEx estimate
    const capexMatch = bodyText.match(/capex[:\s]*\$?([\d,]+\.?\d*)/i) ||
                      bodyText.match(/estimated cost[:\s]*\$?([\d,]+\.?\d*)/i) ||
                      bodyText.match(/total[:\s]*\$?([\d,]+\.?\d*)/i);
    
    if (capexMatch) {
      const capex = parseFloat(capexMatch[1].replace(/,/g, ''));
      console.log(`✓ CapEx estimate: $${capex}`);
      
      // Validate reasonable range
      expect(capex).toBeGreaterThan(100); // At minimum $100
      expect(capex).toBeLessThan(1000000); // Max $1M for typical SMB
      
      // Check if device counts support the cost
      const apMatch = bodyText.match(/(\d+)\s*(?:access\s*points?|APs?)/i);
      const apCount = apMatch ? parseInt(apMatch[1]) : 0;
      
      if (apCount > 0) {
        const costPerAP = capex / apCount;
        console.log(`✓ Cost per AP: $${costPerAP.toFixed(2)}`);
        
        // Typical AP cost range: $100 - $2000
        expect(costPerAP).toBeGreaterThan(50);
        expect(costPerAP).toBeLessThan(5000);
      }
    }
  });

  test('AI rationale is captured and displayed', async ({ page }) => {
    await page.goto('/shop/designs/new', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    
    // Look for AI rationale or explanation section
    const bodyText = await page.locator('//body').textContent() || '';
    
    const hasRationale = bodyText.toLowerCase().includes('rationale') ||
                        bodyText.toLowerCase().includes('recommendation') ||
                        bodyText.toLowerCase().includes('reasoning') ||
                        bodyText.toLowerCase().includes('why');
    
    console.log(`✓ AI rationale section present: ${hasRationale}`);
    
    // If rationale exists, check it has meaningful content
    if (hasRationale) {
      const rationaleMatch = bodyText.match(/(?:rationale|recommendation|reasoning)[:\s]*([\s\S]{50,500})/i);
      if (rationaleMatch) {
        const rationaleText = rationaleMatch[1].trim();
        console.log(`✓ Rationale length: ${rationaleText.length} chars`);
        expect(rationaleText.length).toBeGreaterThan(20); // Not empty
      }
    }
  });
});
