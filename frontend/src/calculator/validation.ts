import { DEFAULT_OPTIONAL_OVERRIDES, DEFAULT_SWITCH_PORTS } from './constants';
import {
  NetworkCalculatorInput,
  NormalizedNetworkCalculatorInput,
  OptionalOverrides,
  PricingInputs,
} from './types';

export const assertFiniteNumber = (
  value: unknown,
  fieldName: string,
  options: { min?: number; greaterThanZero?: boolean } = {},
): number => {
  if (typeof value !== 'number' || Number.isNaN(value) || !Number.isFinite(value)) {
    throw new Error(`Invalid ${fieldName}: must be a finite number.`);
  }

  if (options.greaterThanZero && value <= 0) {
    throw new Error(`Invalid ${fieldName}: must be greater than 0.`);
  }

  if (options.min !== undefined && value < options.min) {
    throw new Error(`Invalid ${fieldName}: must be >= ${options.min}.`);
  }

  return value;
};

export const assertValidEnum = <T extends string>(value: string, allowed: readonly T[], fieldName: string): T => {
  if (!allowed.includes(value as T)) {
    throw new Error(`Invalid ${fieldName}: '${value}'. Allowed values are: ${allowed.join(', ')}.`);
  }
  return value as T;
};

export const validatePricing = (pricing: PricingInputs): PricingInputs => ({
  indoorAPPrice: assertFiniteNumber(pricing.indoorAPPrice, 'pricing.indoorAPPrice', { min: 0 }),
  licensePrice: assertFiniteNumber(pricing.licensePrice, 'pricing.licensePrice', { min: 0 }),
  cablingCostPerDrop: assertFiniteNumber(pricing.cablingCostPerDrop, 'pricing.cablingCostPerDrop', { min: 0 }),
  laborHoursPerAP: assertFiniteNumber(pricing.laborHoursPerAP, 'pricing.laborHoursPerAP', { min: 0 }),
  laborRate: assertFiniteNumber(pricing.laborRate, 'pricing.laborRate', { min: 0 }),
  switchPrice: assertFiniteNumber(pricing.switchPrice, 'pricing.switchPrice', { min: 0 }),
  upsPrice: assertFiniteNumber(pricing.upsPrice, 'pricing.upsPrice', { min: 0 }),
  markupPct: assertFiniteNumber(pricing.markupPct, 'pricing.markupPct', { min: 0 }),
  taxPct: assertFiniteNumber(pricing.taxPct, 'pricing.taxPct', { min: 0 }),
});

export const validateOverrides = (overrides?: OptionalOverrides): Required<OptionalOverrides> => {
  const merged = { ...DEFAULT_OPTIONAL_OVERRIDES, ...(overrides ?? {}) };

  return {
    concurrencyFactor: assertFiniteNumber(merged.concurrencyFactor, 'optionalOverrides.concurrencyFactor', { min: 0 }),
    txPowerDbm: assertFiniteNumber(merged.txPowerDbm, 'optionalOverrides.txPowerDbm'),
    txGainDbi: assertFiniteNumber(merged.txGainDbi, 'optionalOverrides.txGainDbi'),
    targetRssiDbm: assertFiniteNumber(merged.targetRssiDbm, 'optionalOverrides.targetRssiDbm'),
    fadeMarginDb: assertFiniteNumber(merged.fadeMarginDb, 'optionalOverrides.fadeMarginDb', { min: 0 }),
    cableLossDb: assertFiniteNumber(merged.cableLossDb, 'optionalOverrides.cableLossDb', { min: 0 }),
    floorLossDb: assertFiniteNumber(merged.floorLossDb, 'optionalOverrides.floorLossDb', { min: 0 }),
    packingEfficiency: assertFiniteNumber(merged.packingEfficiency, 'optionalOverrides.packingEfficiency', { greaterThanZero: true }),
    airtimeEfficiency: assertFiniteNumber(merged.airtimeEfficiency, 'optionalOverrides.airtimeEfficiency', { greaterThanZero: true }),
    channelReuse: assertFiniteNumber(merged.channelReuse, 'optionalOverrides.channelReuse', { greaterThanZero: true }),
    overheadFactor: assertFiniteNumber(merged.overheadFactor, 'optionalOverrides.overheadFactor', { greaterThanZero: true }),
    redundancyFactor: assertFiniteNumber(merged.redundancyFactor, 'optionalOverrides.redundancyFactor', { greaterThanZero: true }),
    frequencyMHz: assertFiniteNumber(merged.frequencyMHz, 'optionalOverrides.frequencyMHz', { greaterThanZero: true }),
  };
};

export const validateAndNormalizeInput = (input: NetworkCalculatorInput): NormalizedNetworkCalculatorInput => {
  if (!input || typeof input !== 'object') {
    throw new Error('Invalid input: payload is required.');
  }

  if (!input.businessType || input.businessType.trim().length === 0) {
    throw new Error('Invalid businessType: must be a non-empty string.');
  }

  const environmentType = assertValidEnum(input.environmentType, ['office', 'hospital', 'warehouse', 'stadium', 'custom'], 'environmentType');
  const obstructionType = assertValidEnum(input.obstructionType, ['open', 'standard', 'dense', 'very_dense'], 'obstructionType');
  const wifiStandard = assertValidEnum(input.wifiStandard, ['wifi5', 'wifi6', 'wifi6e', 'wifi7'], 'wifiStandard');

  const normalized: NormalizedNetworkCalculatorInput = {
    businessType: input.businessType.trim(),
    environmentType,
    totalFloorAreaSqft: assertFiniteNumber(input.totalFloorAreaSqft, 'totalFloorAreaSqft', { greaterThanZero: true }),
    numberOfFloors: input.numberOfFloors,
    obstructionType,
    wifiStandard,
    totalUsers: assertFiniteNumber(input.totalUsers, 'totalUsers', { greaterThanZero: true }),
    devicesPerUser: assertFiniteNumber(input.devicesPerUser, 'devicesPerUser', { greaterThanZero: true }),
    throughputPerUserMbps: assertFiniteNumber(input.throughputPerUserMbps, 'throughputPerUserMbps', { greaterThanZero: true }),
    redundancyEnabled: input.redundancyEnabled ?? false,
    switchPorts: assertFiniteNumber(input.switchPorts ?? DEFAULT_SWITCH_PORTS, 'switchPorts', { greaterThanZero: true }),
    upsRequired: input.upsRequired ?? false,
    pricing: validatePricing(input.pricing),
    optionalOverrides: validateOverrides(input.optionalOverrides),
  };

  if (normalized.numberOfFloors !== undefined) {
    normalized.numberOfFloors = assertFiniteNumber(normalized.numberOfFloors, 'numberOfFloors', { greaterThanZero: true });
  }

  return normalized;
};
