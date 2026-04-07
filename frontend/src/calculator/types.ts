export type EnvironmentType = 'office' | 'hospital' | 'warehouse' | 'stadium' | 'custom';
export type ObstructionType = 'open' | 'standard' | 'dense' | 'very_dense';
export type WifiStandard = 'wifi5' | 'wifi6' | 'wifi6e' | 'wifi7';

export interface PricingInputs {
  indoorAPPrice: number;
  licensePrice: number;
  cablingCostPerDrop: number;
  laborHoursPerAP: number;
  laborRate: number;
  switchPrice: number;
  upsPrice: number;
  markupPct: number;
  taxPct: number;
}

export interface OptionalOverrides {
  concurrencyFactor?: number;
  txPowerDbm?: number;
  txGainDbi?: number;
  targetRssiDbm?: number;
  fadeMarginDb?: number;
  cableLossDb?: number;
  floorLossDb?: number;
  packingEfficiency?: number;
  airtimeEfficiency?: number;
  channelReuse?: number;
  overheadFactor?: number;
  redundancyFactor?: number;
  frequencyMHz?: number;
}

export interface NetworkCalculatorInput {
  businessType: string;
  environmentType: EnvironmentType;
  totalFloorAreaSqft: number;
  numberOfFloors?: number;
  obstructionType: ObstructionType;
  wifiStandard: WifiStandard;
  totalUsers: number;
  devicesPerUser: number;
  throughputPerUserMbps: number;
  redundancyEnabled?: boolean;
  switchPorts?: number;
  upsRequired?: boolean;
  pricing: PricingInputs;
  optionalOverrides?: OptionalOverrides;
}

export interface NormalizedNetworkCalculatorInput {
  businessType: string;
  environmentType: EnvironmentType;
  totalFloorAreaSqft: number;
  numberOfFloors?: number;
  obstructionType: ObstructionType;
  wifiStandard: WifiStandard;
  totalUsers: number;
  devicesPerUser: number;
  throughputPerUserMbps: number;
  redundancyEnabled: boolean;
  switchPorts: number;
  upsRequired: boolean;
  pricing: PricingInputs;
  optionalOverrides: Required<OptionalOverrides>;
}

export interface NetworkCalculatorResult {
  inputsNormalized: NormalizedNetworkCalculatorInput;
  lookupsUsed: {
    obstructionLossDb: number;
    concurrencyFactor: number;
    standardThroughputMbps: number;
  };
  rfModel: {
    allowedPathLossDb: number;
    estimatedRadiusFt: number;
    effectiveCellAreaSqft: number;
  };
  capacityModel: {
    effectiveUsers: number;
    totalDevices: number;
    usableThroughputMbps: number;
    requiredThroughputMbps: number;
  };
  counts: {
    coverageAPs: number;
    capacityAPs: number;
    indoorAPs: number;
    indoorAPsFinal: number;
    switchCount: number;
  };
  costs: {
    indoorHardware: number;
    licenses: number;
    cabling: number;
    labor: number;
    switchCost: number;
    upsCost: number;
    capExBase: number;
    capExWithMarkup: number;
    capExFinal: number;
  };
  summary: {
    recommendedIndoorAPs: number;
    recommendedSwitches: number;
    estimatedCapEx: number;
  };
}
