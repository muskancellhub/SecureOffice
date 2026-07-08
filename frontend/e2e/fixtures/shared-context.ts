/**
 * SHARED CONTEXT FOR E2E PHASES
 * 
 * This file maintains state between test phases so that:
 * - Phase 1 can use data from Phase 0
 * - Phase 2 can use data from Phase 1
 * - Phase 3 can use data from Phase 2
 * - And so on...
 * 
 * Usage:
 * 
 * // Phase 0 - Save data
 * import { phaseContext } from '../fixtures/shared-context';
 * phaseContext.phase0.businessType = 'Restaurant / QSR';
 * phaseContext.phase0.calculatorData = { ... };
 * 
 * // Phase 1 - Read Phase 0 data
 * import { phaseContext } from '../fixtures/shared-context';
 * console.log('Using business type:', phaseContext.phase0.businessType);
 * 
 * IMPORTANT: This is in-memory only. For cross-session persistence,
 * tests also use localStorage (which is saved in browser context).
 */

export interface Phase0Context {
  // Business Intake Data
  businessType: string | null;
  locations: string | null;
  squareFootage: string | null;
  employees: string | null;
  internetType: string | null;
  
  // Calculator Results
  calculatorData: {
    accessPoints: number;
    switches: number;
    routers: number;
    estimatedCost: number;
  } | null;
  
  // Flags
  intakeCompleted: boolean;
  calculatorCompleted: boolean;
}

export interface Phase1Context {
  // Design Builder Data
  designId: string | null;
  designName: string | null;
  
  // BOM Data
  bomItems: Array<{
    name: string;
    quantity: number;
    price: number;
  }> | null;
  
  bomTotal: number | null;
  
  // Design Status
  designSubmitted: boolean;
  designStatus: 'draft' | 'submitted' | 'in_review' | 'approved' | 'completed' | null;
}

export interface Phase2Context {
  // Cart & Commerce Data
  cartItems: Array<{
    productId: string;
    productName: string;
    quantity: number;
    price: number;
  }> | null;
  
  cartTotal: number | null;
  
  // Order Data
  orderId: string | null;
  orderTotal: number | null;
  orderStatus: 'pending' | 'processing' | 'completed' | 'cancelled' | null;
}

export interface Phase3Context {
  // Quote Data
  quoteId: string | null;
  quoteNumber: string | null;
  quoteTotal: number | null;
  quoteStatus: 'pending' | 'approved' | 'rejected' | 'expired' | null;
  
  // Quote Items (from design BOM)
  quoteItems: Array<{
    productName: string;
    quantity: number;
    price: number;
  }> | null;
}

export interface Phase4Context {
  // Onboarding Data
  onboardingCompleted: boolean;
  organizationName: string | null;
  industryType: string | null;
  
  // User Preferences
  notificationPreferences: {
    email: boolean;
    sms: boolean;
    push: boolean;
  } | null;
}

export interface Phase5Context {
  // Tenant Isolation Data
  company1DesignIds: string[];
  company2DesignIds: string[];
  
  // Security Tests
  unauthorizedAccessAttempts: number;
  isolationVerified: boolean;
}

export interface Phase6Context {
  // Admin Design Ops Data
  submittedDesignIds: string[];
  reviewedDesignIds: string[];
  approvedDesignIds: string[];
  
  // Admin Actions
  internalNotes: Array<{
    designId: string;
    note: string;
    timestamp: string;
  }>;
}

export interface Phase7Context {
  // AI Features Data
  chatbotInteractions: number;
  aiRecommendations: {
    accessPoints: number;
    switches: number;
    routers: number;
  } | null;
  
  // Intake Chat
  aiIntakeCompleted: boolean;
}

export interface Phase8Context {
  // Extended Auth Data
  otpLoginAttempts: number;
  oauthLoginAttempts: number;
  sessionTokens: string[];
  
  // Session Management
  refreshTokenUsed: boolean;
  sessionExpired: boolean;
}

export interface Phase9Context {
  // Order Tracking Data
  trackedOrderIds: string[];
  invoiceDownloaded: boolean;
  
  // Order Details
  orderLineItems: Array<{
    productName: string;
    quantity: number;
    price: number;
  }> | null;
}

export interface Phase10Context {
  // Edge Cases & Error Handling
  errorsCaught: number;
  networkErrorsHandled: number;
  validationsPassed: number;
  
  // Browser Compatibility
  testedOnMobile: boolean;
  testedOnTablet: boolean;
  testedOnDesktop: boolean;
}

/**
 * GLOBAL PHASE CONTEXT
 * 
 * This object stores data from all phases.
 * Each phase writes to its own section and reads from previous phases.
 */
export const phaseContext = {
  phase0: {
    businessType: null,
    locations: null,
    squareFootage: null,
    employees: null,
    internetType: null,
    calculatorData: null,
    intakeCompleted: false,
    calculatorCompleted: false,
  } as Phase0Context,
  
  phase1: {
    designId: null,
    designName: null,
    bomItems: null,
    bomTotal: null,
    designSubmitted: false,
    designStatus: null,
  } as Phase1Context,
  
  phase2: {
    cartItems: null,
    cartTotal: null,
    orderId: null,
    orderTotal: null,
    orderStatus: null,
  } as Phase2Context,
  
  phase3: {
    quoteId: null,
    quoteNumber: null,
    quoteTotal: null,
    quoteStatus: null,
    quoteItems: null,
  } as Phase3Context,
  
  phase4: {
    onboardingCompleted: false,
    organizationName: null,
    industryType: null,
    notificationPreferences: null,
  } as Phase4Context,
  
  phase5: {
    company1DesignIds: [],
    company2DesignIds: [],
    unauthorizedAccessAttempts: 0,
    isolationVerified: false,
  } as Phase5Context,
  
  phase6: {
    submittedDesignIds: [],
    reviewedDesignIds: [],
    approvedDesignIds: [],
    internalNotes: [],
  } as Phase6Context,
  
  phase7: {
    chatbotInteractions: 0,
    aiRecommendations: null,
    aiIntakeCompleted: false,
  } as Phase7Context,
  
  phase8: {
    otpLoginAttempts: 0,
    oauthLoginAttempts: 0,
    sessionTokens: [],
    refreshTokenUsed: false,
    sessionExpired: false,
  } as Phase8Context,
  
  phase9: {
    trackedOrderIds: [],
    invoiceDownloaded: false,
    orderLineItems: null,
  } as Phase9Context,
  
  phase10: {
    errorsCaught: 0,
    networkErrorsHandled: 0,
    validationsPassed: 0,
    testedOnMobile: false,
    testedOnTablet: false,
    testedOnDesktop: false,
  } as Phase10Context,
};

/**
 * HELPER FUNCTIONS
 */

/**
 * Reset all phase context (use at start of test suite)
 */
export function resetPhaseContext() {
  phaseContext.phase0 = {
    businessType: null,
    locations: null,
    squareFootage: null,
    employees: null,
    internetType: null,
    calculatorData: null,
    intakeCompleted: false,
    calculatorCompleted: false,
  };
  
  phaseContext.phase1 = {
    designId: null,
    designName: null,
    bomItems: null,
    bomTotal: null,
    designSubmitted: false,
    designStatus: null,
  };
  
  // ... reset other phases as needed
}

/**
 * Get localStorage data saved by Phase 0
 * (Use this in Phase 1 to verify intake data exists)
 */
export async function getPhase0LocalStorageData(page: any) {
  const intakeData = await page.evaluate(() => {
    return {
      businessIntake: localStorage.getItem('secureOfficeBusinessIntake'),
      calculatorResults: localStorage.getItem('secureOfficeNetworkEstimateV1'),
      calculatorInput: localStorage.getItem('secureOfficeNetworkEstimateInputV1'),
    };
  });
  
  return {
    businessIntake: intakeData.businessIntake ? JSON.parse(intakeData.businessIntake) : null,
    calculatorResults: intakeData.calculatorResults ? JSON.parse(intakeData.calculatorResults) : null,
    calculatorInput: intakeData.calculatorInput ? JSON.parse(intakeData.calculatorInput) : null,
  };
}

/**
 * Log phase context (for debugging)
 */
export function logPhaseContext(phaseName: string) {
  console.log(`\n========================================`);
  console.log(`📊 Phase Context Summary - ${phaseName}`);
  console.log(`========================================`);
  
  // Phase 0
  if (phaseContext.phase0.intakeCompleted) {
    console.log(`✅ Phase 0: Business Intake - COMPLETED`);
    console.log(`   Business Type: ${phaseContext.phase0.businessType}`);
    console.log(`   Locations: ${phaseContext.phase0.locations}`);
  } else {
    console.log(`⏳ Phase 0: Business Intake - NOT COMPLETED`);
  }
  
  // Phase 1
  if (phaseContext.phase1.designSubmitted) {
    console.log(`✅ Phase 1: Design Builder - COMPLETED`);
    console.log(`   Design ID: ${phaseContext.phase1.designId}`);
    console.log(`   BOM Total: $${phaseContext.phase1.bomTotal}`);
  } else {
    console.log(`⏳ Phase 1: Design Builder - NOT COMPLETED`);
  }
  
  // Phase 2
  if (phaseContext.phase2.orderId) {
    console.log(`✅ Phase 2: Cart & Orders - COMPLETED`);
    console.log(`   Order ID: ${phaseContext.phase2.orderId}`);
    console.log(`   Order Total: $${phaseContext.phase2.orderTotal}`);
  } else {
    console.log(`⏳ Phase 2: Cart & Orders - NOT COMPLETED`);
  }
  
  console.log(`========================================\n`);
}

/**
 * PHASE DEPENDENCY CHECKER
 * 
 * Use this to verify that required previous phases have completed
 */
export function checkPhaseDependencies(currentPhase: number): {
  canProceed: boolean;
  missingPhases: string[];
} {
  const missingPhases: string[] = [];
  
  // Phase 1 requires Phase 0
  if (currentPhase >= 1 && !phaseContext.phase0.intakeCompleted) {
    missingPhases.push('Phase 0 (Business Intake)');
  }
  
  // Phase 2 can run independently or use Phase 1 data
  // (no hard dependency)
  
  // Phase 3 requires Phase 1 (quotes are based on designs)
  if (currentPhase === 3 && !phaseContext.phase1.designSubmitted) {
    missingPhases.push('Phase 1 (Design Builder)');
  }
  
  return {
    canProceed: missingPhases.length === 0,
    missingPhases,
  };
}
