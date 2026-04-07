import { describe, expect, it } from 'vitest';
import {
  calculateCapEx,
  calculateCapacityAps,
  calculateCoverageAps,
  calculateNetworkEstimate,
  calculateSwitchCount,
  getConcurrencyFactor,
  getObstructionLoss,
  getStandardThroughput,
  validateAndNormalizeInput,
} from '../index';
import { NetworkCalculatorInput } from '../types';

const sampleInput: NetworkCalculatorInput = {
  businessType: 'QSR',
  environmentType: 'office',
  totalFloorAreaSqft: 12000,
  obstructionType: 'standard',
  wifiStandard: 'wifi6',
  totalUsers: 80,
  devicesPerUser: 1.5,
  throughputPerUserMbps: 4,
  redundancyEnabled: true,
  switchPorts: 24,
  upsRequired: true,
  pricing: {
    indoorAPPrice: 850,
    licensePrice: 120,
    cablingCostPerDrop: 180,
    laborHoursPerAP: 2,
    laborRate: 95,
    switchPrice: 1100,
    upsPrice: 450,
    markupPct: 15,
    taxPct: 8.25,
  },
};

describe('lookup functions', () => {
  it('returns lookup values for obstruction, wifi throughput, and concurrency', () => {
    expect(getObstructionLoss('open')).toBe(0);
    expect(getObstructionLoss('dense')).toBe(12);
    expect(getStandardThroughput('wifi6e')).toBe(900);
    expect(getConcurrencyFactor('office')).toBe(0.6);
    expect(getConcurrencyFactor('custom', 0.72)).toBe(0.72);
    expect(getConcurrencyFactor('custom')).toBe(0.6);
  });
});

describe('core count calculations', () => {
  it('calculates coverage AP count via ceil(area/cell)', () => {
    expect(calculateCoverageAps(10000, 2500)).toBe(4);
  });

  it('calculates capacity AP count and intermediate values', () => {
    const result = calculateCapacityAps(100, 2, 3, 0.6, 600, 0.55, 0.8, 1.3);
    expect(result.effectiveUsers).toBe(60);
    expect(result.totalDevices).toBe(120);
    expect(result.usableThroughputMbps).toBe(264);
    expect(result.requiredThroughputMbps).toBe(468);
    expect(result.capacityAPs).toBe(2);
  });

  it('calculates switch count via ceil(totalAPs/switchPorts)', () => {
    expect(calculateSwitchCount(25, 24)).toBe(2);
  });
});

describe('cost model', () => {
  it('calculates capex components with markup and tax', () => {
    const costs = calculateCapEx({
      indoorAPsFinal: 3,
      switchCount: 1,
      upsRequired: true,
      pricing: sampleInput.pricing,
    });

    expect(costs).toEqual({
      indoorHardware: 2550,
      licenses: 360,
      cabling: 540,
      labor: 570,
      switchCost: 1100,
      upsCost: 450,
      capExBase: 5570,
      capExWithMarkup: 6405.5,
      capExFinal: 6933.95,
    });
  });
});

describe('validation', () => {
  it('rejects negative and invalid values', () => {
    expect(() =>
      validateAndNormalizeInput({
        ...sampleInput,
        totalUsers: -1,
      }),
    ).toThrow(/totalUsers/);

    expect(() =>
      validateAndNormalizeInput({
        ...sampleInput,
        environmentType: 'unknown' as NetworkCalculatorInput['environmentType'],
      }),
    ).toThrow(/environmentType/);
  });
});

describe('end-to-end network estimate', () => {
  it('returns deterministic counts and capex for the sample payload', () => {
    const estimate = calculateNetworkEstimate(sampleInput);

    // Sample output contract assertions (V1 scope)
    expect(estimate.lookupsUsed).toEqual({
      obstructionLossDb: 6,
      concurrencyFactor: 0.6,
      standardThroughputMbps: 600,
    });

    expect(estimate.counts).toEqual({
      coverageAPs: 2,
      capacityAPs: 2,
      indoorAPs: 2,
      indoorAPsFinal: 3,
      switchCount: 1,
    });

    expect(estimate.summary).toEqual({
      recommendedIndoorAPs: 3,
      recommendedSwitches: 1,
      estimatedCapEx: 6933.95,
    });

    expect(estimate.rfModel.estimatedRadiusFt).toBeGreaterThan(50);
    expect(estimate.rfModel.estimatedRadiusFt).toBeLessThan(60);
  });

  it('applies redundancy only when enabled', () => {
    const withoutRedundancy = calculateNetworkEstimate({
      ...sampleInput,
      redundancyEnabled: false,
      upsRequired: false,
    });

    expect(withoutRedundancy.counts.indoorAPs).toBe(2);
    expect(withoutRedundancy.counts.indoorAPsFinal).toBe(2);
  });
});
