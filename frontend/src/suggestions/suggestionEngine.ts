import { retrieveCatalogItems } from './retriever';
import type {
  CalculatorResult,
  CatalogItem,
  ProductRetriever,
  RetrievedCandidates,
  SelectedProducts,
  Vendor,
  WifiStandard,
} from './types';

const WIFI_ORDER: WifiStandard[] = ['wifi5', 'wifi6', 'wifi6e', 'wifi7'];
const CELLULAR_PREFERRED_VENDORS: Vendor[] = ['InHand', 'SkyMirr'];

const numericPrice = (item: CatalogItem): number => {
  if (typeof item.price === 'number' && Number.isFinite(item.price) && item.price >= 0) {
    return item.price;
  }
  return Number.POSITIVE_INFINITY;
};

const isIndoorOutdoorCompatible = (
  requested: 'indoor' | 'outdoor' | 'mixed' | undefined,
  itemValue: CatalogItem['indoorOutdoor'],
): boolean => {
  if (!requested || requested === 'mixed') return true;
  if (!itemValue || itemValue === 'both') return true;
  return requested === itemValue;
};

const toRetrieverIndoorOutdoor = (
  value: 'indoor' | 'outdoor' | 'mixed' | undefined,
): 'indoor' | 'outdoor' | 'both' | undefined => {
  if (!value || value === 'mixed') return 'both';
  return value;
};

const resolveRequiredApCount = (calculatorResult: CalculatorResult): number => {
  const byCounts = Number(calculatorResult.counts?.indoorAPsFinal || 0);
  if (byCounts > 0) return Math.floor(byCounts);
  const bySummary = Number(calculatorResult.summary?.recommendedIndoorAPs || 0);
  if (bySummary > 0) return Math.floor(bySummary);
  return 0;
};

const resolveSwitchCount = (calculatorResult: CalculatorResult): number => {
  const byCounts = Number(calculatorResult.counts?.switchCount || 0);
  if (byCounts > 0) return Math.floor(byCounts);
  const bySummary = Number(calculatorResult.summary?.recommendedSwitches || 0);
  if (bySummary > 0) return Math.floor(bySummary);
  return 0;
};

const wifiDistance = (candidate: WifiStandard | undefined, target: WifiStandard | undefined): number => {
  if (!candidate || !target) return 0;
  const candidateIndex = WIFI_ORDER.indexOf(candidate);
  const targetIndex = WIFI_ORDER.indexOf(target);
  if (candidateIndex < 0 || targetIndex < 0) return 0;
  return Math.abs(candidateIndex - targetIndex);
};

export type CandidateScoreContext = {
  preferredVendor?: Vendor;
  allowedVendors?: Vendor[];
  targetWifiStandard?: WifiStandard;
  indoorOutdoor?: 'indoor' | 'outdoor' | 'mixed';
  preferCheapest?: boolean;
  requiredPorts?: number;
  needsPoe?: boolean;
  preferCellularVendors?: boolean;
};

export const scoreProductCandidate = (item: CatalogItem, ctx: CandidateScoreContext): number => {
  let score = 0;

  if (ctx.allowedVendors && ctx.allowedVendors.length > 0 && !ctx.allowedVendors.includes(item.vendor)) {
    return -1000;
  }

  if (ctx.preferredVendor && item.vendor === ctx.preferredVendor) score += 55;
  if (ctx.targetWifiStandard) {
    if (item.wifiStandard === ctx.targetWifiStandard) score += 32;
    else score += Math.max(0, 20 - wifiDistance(item.wifiStandard, ctx.targetWifiStandard) * 8);
  }

  if (ctx.preferCellularVendors && CELLULAR_PREFERRED_VENDORS.includes(item.vendor)) score += 24;
  if (item.smbFit) score += 18;
  if (item.pricingBasis === 'public' || item.pricingBasis === 'street') score += 12;
  if (!item.price || !Number.isFinite(item.price) || item.price < 0) score -= 10;

  if (ctx.needsPoe) {
    if (item.poe) score += 26;
    else score -= 20;
  }

  if (ctx.requiredPorts && ctx.requiredPorts > 0) {
    const ports = item.ports || 0;
    if (ports >= ctx.requiredPorts) score += 28;
    else if (ports > 0) score += Math.max(-16, 8 - (ctx.requiredPorts - ports));
    else score -= 8;
  }

  if (isIndoorOutdoorCompatible(ctx.indoorOutdoor, item.indoorOutdoor)) score += 10;
  else score -= 20;

  const price = numericPrice(item);
  if (Number.isFinite(price)) {
    score += ctx.preferCheapest ? Math.max(0, 50 - price / 18) : Math.max(0, 8 - price / 300);
  }

  return score;
};

const sortByScore = (candidates: CatalogItem[], ctx: CandidateScoreContext): CatalogItem[] => {
  return [...candidates].sort((a, b) => {
    const scoreDiff = scoreProductCandidate(b, ctx) - scoreProductCandidate(a, ctx);
    if (scoreDiff !== 0) return scoreDiff;

    const priceDiff = numericPrice(a) - numericPrice(b);
    if (priceDiff !== 0) return priceDiff;

    return `${a.vendor}-${a.model}`.localeCompare(`${b.vendor}-${b.model}`);
  });
};

const pickCheapest = (candidates: CatalogItem[]): CatalogItem | undefined => {
  if (candidates.length === 0) return undefined;
  return [...candidates].sort((a, b) => numericPrice(a) - numericPrice(b))[0];
};

const vendorFilter = (preferred: Vendor | undefined, allowed: Vendor[] | undefined): Vendor[] | undefined => {
  if (preferred && allowed && allowed.length > 0) {
    return allowed.includes(preferred) ? [preferred] : undefined;
  }
  if (preferred) return [preferred];
  return allowed && allowed.length > 0 ? allowed : undefined;
};

export type SuggestionResult = {
  retrievedCandidates: RetrievedCandidates;
  selectedProducts: SelectedProducts;
  notes: string[];
  warnings: string[];
};

export const suggestAccessPoint = (
  retriever: ProductRetriever,
  params: {
    preferredVendor?: Vendor;
    allowedVendors?: Vendor[];
    targetWifiStandard?: WifiStandard;
    indoorOutdoor?: 'indoor' | 'outdoor' | 'mixed';
    preferCheapest?: boolean;
  },
): { candidates: CatalogItem[]; selected?: CatalogItem; notes: string[]; warnings: string[] } => {
  const notes: string[] = [];
  const warnings: string[] = [];

  const preferredCandidates = retrieveCatalogItems(retriever, {
    categories: ['wifi_ap'],
    vendors: vendorFilter(params.preferredVendor, params.allowedVendors),
    wifiStandard: params.targetWifiStandard,
    indoorOutdoor: toRetrieverIndoorOutdoor(params.indoorOutdoor),
    smbOnly: true,
    limit: 40,
  });

  const fallbackCandidates = preferredCandidates.length > 0
    ? preferredCandidates
    : retrieveCatalogItems(retriever, {
      categories: ['wifi_ap'],
      vendors: params.allowedVendors,
      wifiStandard: params.targetWifiStandard,
      indoorOutdoor: toRetrieverIndoorOutdoor(params.indoorOutdoor),
      smbOnly: true,
      limit: 40,
    });

  const broadFallback = fallbackCandidates.length > 0
    ? fallbackCandidates
    : retrieveCatalogItems(retriever, {
      categories: ['wifi_ap'],
      vendors: params.allowedVendors,
      indoorOutdoor: toRetrieverIndoorOutdoor(params.indoorOutdoor),
      limit: 40,
    });

  if (preferredCandidates.length === 0 && params.preferredVendor) {
    warnings.push(`No AP found for preferred vendor ${params.preferredVendor}; used cross-vendor fallback.`);
  }

  if (broadFallback.length === 0) {
    warnings.push('No Wi-Fi AP candidates found in catalog.');
    return { candidates: [], selected: undefined, notes, warnings };
  }

  const pool = params.targetWifiStandard
    ? broadFallback.filter((item) => !item.wifiStandard || item.wifiStandard === params.targetWifiStandard)
    : broadFallback;

  if (params.targetWifiStandard && pool.length === 0) {
    warnings.push(`No AP exactly matched ${params.targetWifiStandard}; using closest available AP.`);
  }

  const rankingPool = pool.length > 0 ? pool : broadFallback;
  const selected = params.preferCheapest
    ? pickCheapest(rankingPool)
    : sortByScore(rankingPool, {
      preferredVendor: params.preferredVendor,
      allowedVendors: params.allowedVendors,
      targetWifiStandard: params.targetWifiStandard,
      indoorOutdoor: params.indoorOutdoor,
      preferCheapest: params.preferCheapest,
    })[0];

  if (selected) notes.push(`Selected AP ${selected.vendor} ${selected.model}.`);

  return { candidates: broadFallback, selected, notes, warnings };
};

export const suggestSwitch = (
  retriever: ProductRetriever,
  params: {
    requiredApCount: number;
    calculatorSwitchCount: number;
    preferredVendor?: Vendor;
    allowedVendors?: Vendor[];
    preferCheapest?: boolean;
  },
): { candidates: CatalogItem[]; selected?: CatalogItem; quantity: number; notes: string[]; warnings: string[] } => {
  const notes: string[] = [];
  const warnings: string[] = [];

  const preferredCandidates = retrieveCatalogItems(retriever, {
    categories: ['switch'],
    vendors: vendorFilter(params.preferredVendor, params.allowedVendors),
    smbOnly: true,
    limit: 40,
  });

  const fallbackCandidates = preferredCandidates.length > 0
    ? preferredCandidates
    : retrieveCatalogItems(retriever, {
      categories: ['switch'],
      vendors: params.allowedVendors,
      smbOnly: true,
      limit: 40,
    });

  if (preferredCandidates.length === 0 && params.preferredVendor) {
    warnings.push(`No switch found for preferred vendor ${params.preferredVendor}; used cross-vendor fallback.`);
  }

  if (fallbackCandidates.length === 0) {
    warnings.push('No switch candidates found in catalog.');
    return {
      candidates: [],
      selected: undefined,
      quantity: Math.max(1, params.calculatorSwitchCount || 1),
      notes,
      warnings,
    };
  }

  const suitableByPorts = fallbackCandidates.filter((item) => (item.ports || 0) >= params.requiredApCount);
  const pool = suitableByPorts.length > 0 ? suitableByPorts : fallbackCandidates;

  if (suitableByPorts.length === 0) {
    warnings.push(`No switch had ports >= required AP count (${params.requiredApCount}); using practical fallback.`);
  }

  const selected = params.preferCheapest
    ? pickCheapest(pool)
    : sortByScore(pool, {
      preferredVendor: params.preferredVendor,
      allowedVendors: params.allowedVendors,
      requiredPorts: params.requiredApCount,
      needsPoe: true,
      preferCheapest: params.preferCheapest,
    })[0];

  let quantity = Math.max(1, params.calculatorSwitchCount || 1);
  if (selected && (selected.ports || 0) > 0 && params.requiredApCount > 0) {
    const byPorts = Math.ceil(params.requiredApCount / (selected.ports || 1));
    const adjusted = Math.max(quantity, byPorts);
    if (adjusted > quantity) {
      notes.push(`Adjusted switch quantity from ${quantity} to ${adjusted} to satisfy AP port demand.`);
      quantity = adjusted;
    }
  }

  if (selected) notes.push(`Selected switch ${selected.vendor} ${selected.model}.`);

  return { candidates: fallbackCandidates, selected, quantity, notes, warnings };
};

export const suggestGateway = (
  retriever: ProductRetriever,
  params: {
    enabled: boolean;
    preferredVendor?: Vendor;
    allowedVendors?: Vendor[];
    preferCheapest?: boolean;
  },
): { candidates: CatalogItem[]; selected?: CatalogItem; notes: string[]; warnings: string[] } => {
  if (!params.enabled) {
    return { candidates: [], selected: undefined, notes: [], warnings: [] };
  }

  const preferredCandidates = retrieveCatalogItems(retriever, {
    categories: ['gateway', 'firewall', 'security_appliance'],
    vendors: vendorFilter(params.preferredVendor, params.allowedVendors),
    smbOnly: true,
    limit: 40,
  });

  const pool = preferredCandidates.length > 0
    ? preferredCandidates
    : retrieveCatalogItems(retriever, {
      categories: ['gateway', 'firewall', 'security_appliance'],
      vendors: params.allowedVendors,
      smbOnly: true,
      limit: 40,
    });

  const notes: string[] = [];
  const warnings: string[] = [];

  if (preferredCandidates.length === 0 && params.preferredVendor) {
    warnings.push(`No gateway/firewall found for preferred vendor ${params.preferredVendor}; used cross-vendor fallback.`);
  }
  if (pool.length === 0) {
    warnings.push('Gateway/firewall requested but no candidates were found.');
    return { candidates: [], selected: undefined, notes, warnings };
  }

  const selected = params.preferCheapest
    ? pickCheapest(pool)
    : sortByScore(pool, {
      preferredVendor: params.preferredVendor,
      allowedVendors: params.allowedVendors,
      preferCheapest: params.preferCheapest,
    })[0];

  if (selected) notes.push(`Selected gateway/security device ${selected.vendor} ${selected.model}.`);

  return { candidates: pool, selected, notes, warnings };
};

export const suggestCellularBackup = (
  retriever: ProductRetriever,
  params: {
    enabled: boolean;
    preferredVendor?: Vendor;
    allowedVendors?: Vendor[];
    preferCheapest?: boolean;
  },
): { candidates: CatalogItem[]; selected?: CatalogItem; notes: string[]; warnings: string[] } => {
  if (!params.enabled) {
    return { candidates: [], selected: undefined, notes: [], warnings: [] };
  }

  const candidates = retrieveCatalogItems(retriever, {
    categories: ['cellular_gateway', 'router'],
    vendors: params.allowedVendors,
    smbOnly: true,
    limit: 40,
  });

  if (candidates.length === 0) {
    return {
      candidates: [],
      selected: undefined,
      notes: [],
      warnings: ['Cellular backup requested but no cellular/router candidates were found.'],
    };
  }

  const selected = params.preferCheapest
    ? pickCheapest(candidates)
    : sortByScore(candidates, {
      preferredVendor: params.preferredVendor,
      allowedVendors: params.allowedVendors,
      preferCheapest: params.preferCheapest,
      preferCellularVendors: true,
    })[0];

  const notes: string[] = [];
  if (selected) notes.push(`Selected cellular backup device ${selected.vendor} ${selected.model}.`);

  return { candidates, selected, notes, warnings: [] };
};

export const suggestProducts = (
  retriever: ProductRetriever,
  params: {
    calculatorResult: CalculatorResult;
    businessContext: {
      indoorOutdoor?: 'indoor' | 'outdoor' | 'mixed';
      needsGateway?: boolean;
      needsCellularBackup?: boolean;
    };
    selectionPreferences?: {
      preferredVendor?: Vendor | 'auto';
      allowedVendors?: Vendor[];
      preferCheapest?: boolean;
    };
  },
): SuggestionResult => {
  const preferredVendor = params.selectionPreferences?.preferredVendor;
  const resolvedPreferredVendor = preferredVendor && preferredVendor !== 'auto' ? preferredVendor : undefined;
  const allowedVendors = params.selectionPreferences?.allowedVendors;
  const preferCheapest = Boolean(params.selectionPreferences?.preferCheapest);

  const requiredApCount = Math.max(1, resolveRequiredApCount(params.calculatorResult));
  const calculatorSwitchCount = Math.max(1, resolveSwitchCount(params.calculatorResult));

  const apSuggestion = suggestAccessPoint(retriever, {
    preferredVendor: resolvedPreferredVendor,
    allowedVendors,
    targetWifiStandard: params.calculatorResult.inputsNormalized?.wifiStandard,
    indoorOutdoor: params.businessContext.indoorOutdoor,
    preferCheapest,
  });

  const switchSuggestion = suggestSwitch(retriever, {
    requiredApCount,
    calculatorSwitchCount,
    preferredVendor: resolvedPreferredVendor,
    allowedVendors,
    preferCheapest,
  });

  const gatewaySuggestion = suggestGateway(retriever, {
    enabled: Boolean(params.businessContext.needsGateway),
    preferredVendor: resolvedPreferredVendor,
    allowedVendors,
    preferCheapest,
  });

  const cellularSuggestion = suggestCellularBackup(retriever, {
    enabled: Boolean(params.businessContext.needsCellularBackup),
    preferredVendor: resolvedPreferredVendor,
    allowedVendors,
    preferCheapest,
  });

  return {
    retrievedCandidates: {
      aps: apSuggestion.candidates,
      switches: switchSuggestion.candidates,
      gateways: gatewaySuggestion.candidates,
      cellular: cellularSuggestion.candidates,
    },
    selectedProducts: {
      ap: apSuggestion.selected,
      switch: switchSuggestion.selected,
      switchQuantityOverride: switchSuggestion.quantity,
      gateway: gatewaySuggestion.selected,
      cellularBackup: cellularSuggestion.selected,
    },
    notes: [
      ...apSuggestion.notes,
      ...switchSuggestion.notes,
      ...gatewaySuggestion.notes,
      ...cellularSuggestion.notes,
    ],
    warnings: [
      ...apSuggestion.warnings,
      ...switchSuggestion.warnings,
      ...gatewaySuggestion.warnings,
      ...cellularSuggestion.warnings,
    ],
  };
};

