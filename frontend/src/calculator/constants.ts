import { EnvironmentType, ObstructionType, OptionalOverrides, WifiStandard } from './types';

export const OBSTRUCTION_LOSS_DB: Record<ObstructionType, number> = {
  open: 0,
  standard: 6,
  dense: 12,
  very_dense: 20,
};

export const WIFI_STANDARD_THROUGHPUT_MBPS: Record<WifiStandard, number> = {
  wifi5: 400,
  wifi6: 600,
  wifi6e: 900,
  wifi7: 1200,
};

export const ENVIRONMENT_CONCURRENCY_FACTOR: Record<Exclude<EnvironmentType, 'custom'>, number> = {
  office: 0.6,
  hospital: 0.7,
  warehouse: 0.4,
  stadium: 0.8,
};

export const DEFAULT_CONCURRENCY_FACTOR = 0.6;
export const DEFAULT_SWITCH_PORTS = 24;

export const DEFAULT_OPTIONAL_OVERRIDES: Required<OptionalOverrides> = {
  concurrencyFactor: DEFAULT_CONCURRENCY_FACTOR,
  txPowerDbm: 18,
  txGainDbi: 4,
  targetRssiDbm: -67,
  fadeMarginDb: 10,
  cableLossDb: 2,
  floorLossDb: 0,
  packingEfficiency: 0.75,
  airtimeEfficiency: 0.55,
  channelReuse: 0.8,
  overheadFactor: 1.3,
  redundancyFactor: 1.25,
  frequencyMHz: 5000,
};

export const INDOOR_RADIUS_FT_MIN = 10;
export const INDOOR_RADIUS_FT_MAX = 200;
export const FEET_PER_KM = 3280.84;
export const FSPL_CONSTANT_DB = 32.44;
