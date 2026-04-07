import {
  DEFAULT_CONCURRENCY_FACTOR,
  ENVIRONMENT_CONCURRENCY_FACTOR,
  FEET_PER_KM,
  FSPL_CONSTANT_DB,
  INDOOR_RADIUS_FT_MAX,
  INDOOR_RADIUS_FT_MIN,
  OBSTRUCTION_LOSS_DB,
  WIFI_STANDARD_THROUGHPUT_MBPS,
} from './constants';
import {
  EnvironmentType,
  NetworkCalculatorInput,
  NetworkCalculatorResult,
  ObstructionType,
  PricingInputs,
  WifiStandard,
} from './types';
import { validateAndNormalizeInput } from './validation';

const round2 = (value: number): number => Math.round((value + Number.EPSILON) * 100) / 100;

export const getObstructionLoss = (obstructionType: ObstructionType): number => OBSTRUCTION_LOSS_DB[obstructionType];

export const getStandardThroughput = (wifiStandard: WifiStandard): number => WIFI_STANDARD_THROUGHPUT_MBPS[wifiStandard];

export const getConcurrencyFactor = (
  environmentType: EnvironmentType,
  overrideConcurrencyFactor?: number,
): number => {
  if (environmentType === 'custom') {
    return overrideConcurrencyFactor ?? DEFAULT_CONCURRENCY_FACTOR;
  }

  if (overrideConcurrencyFactor !== undefined) {
    return overrideConcurrencyFactor;
  }

  return ENVIRONMENT_CONCURRENCY_FACTOR[environmentType];
};

export const calculateFsplDb = (distanceKm: number, frequencyMHz: number): number =>
  FSPL_CONSTANT_DB + 20 * Math.log10(distanceKm) + 20 * Math.log10(frequencyMHz);

export const calculateIndoorAllowedPathLoss = (params: {
  txPowerDbm: number;
  txGainDbi: number;
  targetRssiDbm: number;
  obstructionLossDb: number;
  fadeMarginDb: number;
  cableLossDb: number;
  floorLossDb: number;
}): number => {
  return (
    params.txPowerDbm +
    params.txGainDbi +
    Math.abs(params.targetRssiDbm) -
    params.obstructionLossDb -
    params.fadeMarginDb -
    params.cableLossDb -
    params.floorLossDb
  );
};

export const invertFsplToDistanceKm = (allowedPathLossDb: number, frequencyMHz: number): number => {
  return 10 ** ((allowedPathLossDb - FSPL_CONSTANT_DB - 20 * Math.log10(frequencyMHz)) / 20);
};

export const convertKmToFeet = (distanceKm: number): number => distanceKm * FEET_PER_KM;

export const clampIndoorRadiusFt = (radiusFt: number): number => Math.min(INDOOR_RADIUS_FT_MAX, Math.max(INDOOR_RADIUS_FT_MIN, radiusFt));

export const calculateEffectiveCellAreaSqft = (indoorRadiusFt: number, packingEfficiency: number): number =>
  Math.PI * indoorRadiusFt ** 2 * packingEfficiency;

export const calculateCoverageAps = (totalFloorAreaSqft: number, effectiveCellAreaSqft: number): number =>
  Math.ceil(totalFloorAreaSqft / effectiveCellAreaSqft);

export const calculateCapacityAps = (
  totalUsers: number,
  devicesPerUser: number,
  throughputPerUserMbps: number,
  concurrencyFactor: number,
  standardThroughputMbps: number,
  airtimeEfficiency: number,
  channelReuse: number,
  overheadFactor: number,
): {
  effectiveUsers: number;
  totalDevices: number;
  usableThroughputMbps: number;
  requiredThroughputMbps: number;
  capacityAPs: number;
} => {
  const effectiveUsers = totalUsers * concurrencyFactor;
  const totalDevices = effectiveUsers * devicesPerUser;
  const usableThroughputMbps = standardThroughputMbps * airtimeEfficiency * channelReuse;
  const requiredThroughputMbps = totalDevices * throughputPerUserMbps * overheadFactor;
  const capacityAPs = Math.ceil(requiredThroughputMbps / usableThroughputMbps);

  return { effectiveUsers, totalDevices, usableThroughputMbps, requiredThroughputMbps, capacityAPs };
};

export const calculateSwitchCount = (totalAPs: number, switchPorts: number): number =>
  Math.ceil(totalAPs / switchPorts);

export const calculateCapEx = (params: {
  indoorAPsFinal: number;
  switchCount: number;
  upsRequired: boolean;
  pricing: PricingInputs;
}): NetworkCalculatorResult['costs'] => {
  const indoorHardware = params.indoorAPsFinal * params.pricing.indoorAPPrice;
  const licenses = params.indoorAPsFinal * params.pricing.licensePrice;
  const cabling = params.indoorAPsFinal * params.pricing.cablingCostPerDrop;
  const labor = params.indoorAPsFinal * params.pricing.laborHoursPerAP * params.pricing.laborRate;
  const switchCost = params.switchCount * params.pricing.switchPrice;
  const upsCost = params.upsRequired ? params.switchCount * params.pricing.upsPrice : 0;
  const capExBase = indoorHardware + licenses + cabling + labor + switchCost + upsCost;
  const capExWithMarkup = capExBase * (1 + params.pricing.markupPct / 100);
  const capExFinal = capExWithMarkup * (1 + params.pricing.taxPct / 100);

  return {
    indoorHardware: round2(indoorHardware),
    licenses: round2(licenses),
    cabling: round2(cabling),
    labor: round2(labor),
    switchCost: round2(switchCost),
    upsCost: round2(upsCost),
    capExBase: round2(capExBase),
    capExWithMarkup: round2(capExWithMarkup),
    capExFinal: round2(capExFinal),
  };
};

export const calculateNetworkEstimate = (input: NetworkCalculatorInput): NetworkCalculatorResult => {
  const inputsNormalized = validateAndNormalizeInput(input);

  const obstructionLossDb = getObstructionLoss(inputsNormalized.obstructionType);
  const standardThroughputMbps = getStandardThroughput(inputsNormalized.wifiStandard);
  const concurrencyFactor = getConcurrencyFactor(
    inputsNormalized.environmentType,
    inputsNormalized.environmentType === 'custom' ? inputsNormalized.optionalOverrides.concurrencyFactor : undefined,
  );

  const allowedPathLossDb = calculateIndoorAllowedPathLoss({
    txPowerDbm: inputsNormalized.optionalOverrides.txPowerDbm,
    txGainDbi: inputsNormalized.optionalOverrides.txGainDbi,
    targetRssiDbm: inputsNormalized.optionalOverrides.targetRssiDbm,
    obstructionLossDb,
    fadeMarginDb: inputsNormalized.optionalOverrides.fadeMarginDb,
    cableLossDb: inputsNormalized.optionalOverrides.cableLossDb,
    floorLossDb: inputsNormalized.optionalOverrides.floorLossDb,
  });

  const estimatedRadiusFt = clampIndoorRadiusFt(
    convertKmToFeet(invertFsplToDistanceKm(allowedPathLossDb, inputsNormalized.optionalOverrides.frequencyMHz)),
  );

  const effectiveCellAreaSqft = calculateEffectiveCellAreaSqft(
    estimatedRadiusFt,
    inputsNormalized.optionalOverrides.packingEfficiency,
  );

  const coverageAPs = calculateCoverageAps(inputsNormalized.totalFloorAreaSqft, effectiveCellAreaSqft);

  const capacity = calculateCapacityAps(
    inputsNormalized.totalUsers,
    inputsNormalized.devicesPerUser,
    inputsNormalized.throughputPerUserMbps,
    concurrencyFactor,
    standardThroughputMbps,
    inputsNormalized.optionalOverrides.airtimeEfficiency,
    inputsNormalized.optionalOverrides.channelReuse,
    inputsNormalized.optionalOverrides.overheadFactor,
  );

  const indoorAPs = Math.max(coverageAPs, capacity.capacityAPs);
  const indoorAPsFinal = inputsNormalized.redundancyEnabled
    ? Math.ceil(indoorAPs * inputsNormalized.optionalOverrides.redundancyFactor)
    : indoorAPs;
  const switchCount = calculateSwitchCount(indoorAPsFinal, inputsNormalized.switchPorts);

  const costs = calculateCapEx({
    indoorAPsFinal,
    switchCount,
    upsRequired: inputsNormalized.upsRequired,
    pricing: inputsNormalized.pricing,
  });

  return {
    inputsNormalized,
    lookupsUsed: {
      obstructionLossDb,
      concurrencyFactor,
      standardThroughputMbps,
    },
    rfModel: {
      allowedPathLossDb: round2(allowedPathLossDb),
      estimatedRadiusFt: round2(estimatedRadiusFt),
      effectiveCellAreaSqft: round2(effectiveCellAreaSqft),
    },
    capacityModel: {
      effectiveUsers: round2(capacity.effectiveUsers),
      totalDevices: round2(capacity.totalDevices),
      usableThroughputMbps: round2(capacity.usableThroughputMbps),
      requiredThroughputMbps: round2(capacity.requiredThroughputMbps),
    },
    counts: {
      coverageAPs,
      capacityAPs: capacity.capacityAPs,
      indoorAPs,
      indoorAPsFinal,
      switchCount,
    },
    costs,
    summary: {
      recommendedIndoorAPs: indoorAPsFinal,
      recommendedSwitches: switchCount,
      estimatedCapEx: costs.capExFinal,
    },
  };
};
