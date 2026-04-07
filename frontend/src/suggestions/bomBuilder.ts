import type {
  BomConfig,
  BomItem,
  BomTotals,
  CableType,
  CalculatorResult,
  CatalogItem,
  ConnectivityType,
  ProductRetriever,
  SelectedProducts,
} from './types';

export type BomBuilderConfig = {
  includeLicense: boolean;
  includeCabling: boolean;
  includeLabor: boolean;
  laborAsFlatItem: boolean;
  includeUps: boolean;
  includeManagedServices: boolean;
  licensePricePerAp: number | null;
  cablingCostPerDrop: number | null;
  laborHoursPerAp: number | null;
  laborRate: number | null;
  installationFlat: number | null;
  upsPrice: number | null;
  managedWifiMonthly: number | null;
  monitoringMonthly: number | null;
};

export type BuildBomItemsInput = {
  calculatorResult: CalculatorResult;
  selectedProducts: SelectedProducts;
  retriever?: ProductRetriever;
  config?: Partial<BomBuilderConfig>;
  /** Office floor area in sqft — used for cable length estimation */
  totalFloorAreaSqft?: number;
};

/** Default per-meter pricing (USD) for each cable standard */
const DEFAULT_CABLE_PRICE_PER_METER: Record<CableType, number> = {
  CAT5: 0.35,
  CAT6: 0.55,
  CAT6e: 0.80,
};

/** Estimate total cable length from office floor area.
 *  Formula: sqrt(area_sqft) × 0.3048 (→ meters) × wired_drops × 1.2 slack */
const estimateCableLengthMeters = (floorAreaSqft: number, wiredDrops: number): number => {
  if (floorAreaSqft <= 0 || wiredDrops <= 0) return 0;
  const avgRunMeters = Math.sqrt(floorAreaSqft) * 0.3048;
  const slackFactor = 1.2;
  return Math.round(avgRunMeters * wiredDrops * slackFactor * 10) / 10;
};

/** Determine connectivity type for a BOM category */
const connectivityForCategory = (category: BomItem['category']): ConnectivityType => {
  switch (category) {
    case 'wifi_ap':
    case 'switch':
    case 'gateway':
      return 'wired';
    case 'cellular_backup':
      return 'cellular';
    case 'cabling':
    case 'labor':
    case 'license':
    case 'managed_service':
    case 'ups':
      return 'na';
    default:
      return 'wired';
  }
};

const DEFAULT_CONFIG: BomBuilderConfig = {
  includeLicense: true,
  includeCabling: true,
  includeLabor: true,
  laborAsFlatItem: false,
  includeUps: false,
  includeManagedServices: false,
  licensePricePerAp: 120,
  cablingCostPerDrop: 180,
  laborHoursPerAp: 2,
  laborRate: 95,
  installationFlat: null,
  upsPrice: 450,
  managedWifiMonthly: 149,
  monitoringMonthly: 99,
};

const toMoneyOrNull = (value: number | null | undefined): number | null => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null;
  return Number(value.toFixed(2));
};

const lineTotal = (quantity: number, unitPrice: number | null): number | null => {
  if (unitPrice === null) return null;
  return Number((quantity * unitPrice).toFixed(2));
};

const getCatalogUnitPrice = (item: CatalogItem | undefined): number | null => {
  if (!item) return null;
  return toMoneyOrNull(item.price ?? null);
};

const resolveApQuantity = (calculatorResult: CalculatorResult): number => {
  const fromCounts = Number(calculatorResult.counts?.indoorAPsFinal || 0);
  if (fromCounts > 0) return Math.floor(fromCounts);
  const fromSummary = Number(calculatorResult.summary?.recommendedIndoorAPs || 0);
  if (fromSummary > 0) return Math.floor(fromSummary);
  return 0;
};

const resolveSwitchQuantity = (calculatorResult: CalculatorResult): number => {
  const fromCounts = Number(calculatorResult.counts?.switchCount || 0);
  if (fromCounts > 0) return Math.floor(fromCounts);
  const fromSummary = Number(calculatorResult.summary?.recommendedSwitches || 0);
  if (fromSummary > 0) return Math.floor(fromSummary);
  return 0;
};

const resolveLicenseProduct = (retriever: ProductRetriever | undefined, preferredVendor: string | undefined): CatalogItem | undefined => {
  if (!retriever) return undefined;

  if (preferredVendor) {
    const vendorCandidates = retriever.retrieveProducts({
      categories: ['license'],
      vendors: [preferredVendor as CatalogItem['vendor']],
      limit: 5,
    });
    if (vendorCandidates.length > 0) return vendorCandidates[0];
  }

  const fallback = retriever.retrieveProducts({
    categories: ['license'],
    limit: 5,
  });
  return fallback[0];
};

const createLineIdGenerator = (): (() => string) => {
  let counter = 0;
  return () => {
    counter += 1;
    return `line-${counter}`;
  };
};

const pushBomLine = (
  lines: BomItem[],
  getId: () => string,
  line: Omit<BomItem, 'id'>,
): void => {
  lines.push({
    id: getId(),
    ...line,
  });
};

export const buildBomItems = (input: BuildBomItemsInput): { bomItems: BomItem[]; notes: string[]; warnings: string[] } => {
  const config: BomBuilderConfig = {
    ...DEFAULT_CONFIG,
    ...(input.config || {}),
  };

  const apQuantity = Math.max(0, resolveApQuantity(input.calculatorResult));
  const switchQuantityBase = Math.max(0, resolveSwitchQuantity(input.calculatorResult));
  const switchQuantity = Math.max(0, input.selectedProducts.switchQuantityOverride || switchQuantityBase);

  const bomItems: BomItem[] = [];
  const notes: string[] = [];
  const warnings: string[] = [];
  const nextLineId = createLineIdGenerator();

  if (apQuantity <= 0) {
    warnings.push('Calculator did not provide a valid AP quantity.');
  } else if (input.selectedProducts.ap) {
    const ap = input.selectedProducts.ap;
    const unitPrice = getCatalogUnitPrice(ap);
    pushBomLine(bomItems, nextLineId, {
      category: 'wifi_ap',
      vendor: ap.vendor,
      model: ap.model,
      quantity: apQuantity,
      unitPrice,
      lineTotal: lineTotal(apQuantity, unitPrice),
      pricingBasis: ap.pricingBasis,
      source: 'catalog',
      connectivity: 'wired', // AP uplink is wired (PoE)
    });
  } else {
    pushBomLine(bomItems, nextLineId, {
      category: 'wifi_ap',
      model: 'Wi-Fi AP (selection missing)',
      quantity: apQuantity,
      unitPrice: null,
      lineTotal: null,
      pricingBasis: 'unknown',
      source: 'placeholder',
      notes: 'No AP candidate was selected.',
      connectivity: 'wired',
    });
    warnings.push('AP quantity exists but no AP product was selected.');
  }

  if (config.includeLicense && apQuantity > 0) {
    const licenseCatalog = resolveLicenseProduct(input.retriever, input.selectedProducts.ap?.vendor);
    if (licenseCatalog) {
      const unitPrice = getCatalogUnitPrice(licenseCatalog);
      pushBomLine(bomItems, nextLineId, {
        category: 'license',
        vendor: licenseCatalog.vendor,
        model: licenseCatalog.model,
        quantity: apQuantity,
        unitPrice,
        lineTotal: lineTotal(apQuantity, unitPrice),
        pricingBasis: licenseCatalog.pricingBasis,
        source: 'catalog',
      });
    } else {
      const unitPrice = toMoneyOrNull(config.licensePricePerAp);
      pushBomLine(bomItems, nextLineId, {
        category: 'license',
        model: 'Wi-Fi License (placeholder)',
        quantity: apQuantity,
        unitPrice,
        lineTotal: lineTotal(apQuantity, unitPrice),
        pricingBasis: 'unknown',
        source: 'placeholder',
        notes: 'No license row found in catalog; placeholder pricing used.',
      });
      warnings.push('License catalog items not found; placeholder license line inserted.');
    }
  }

  if (switchQuantity <= 0) {
    warnings.push('Calculator did not provide a valid switch quantity.');
  } else if (input.selectedProducts.switch) {
    const selectedSwitch = input.selectedProducts.switch;
    const unitPrice = getCatalogUnitPrice(selectedSwitch);
    pushBomLine(bomItems, nextLineId, {
      category: 'switch',
      vendor: selectedSwitch.vendor,
      model: selectedSwitch.model,
      quantity: switchQuantity,
      unitPrice,
      lineTotal: lineTotal(switchQuantity, unitPrice),
      pricingBasis: selectedSwitch.pricingBasis,
      source: 'catalog',
      notes: selectedSwitch.poe ? 'PoE-capable switch selected.' : undefined,
      connectivity: 'wired',
    });
  } else {
    pushBomLine(bomItems, nextLineId, {
      category: 'switch',
      model: 'PoE Switch (selection missing)',
      quantity: switchQuantity,
      unitPrice: null,
      lineTotal: null,
      pricingBasis: 'unknown',
      source: 'placeholder',
      notes: 'No switch candidate was selected.',
      connectivity: 'wired',
    });
    warnings.push('Switch quantity exists but no switch product was selected.');
  }

  if (input.selectedProducts.gateway) {
    const gateway = input.selectedProducts.gateway;
    const unitPrice = getCatalogUnitPrice(gateway);
    pushBomLine(bomItems, nextLineId, {
      category: 'gateway',
      vendor: gateway.vendor,
      model: gateway.model,
      quantity: 1,
      unitPrice,
      lineTotal: lineTotal(1, unitPrice),
      pricingBasis: gateway.pricingBasis,
      source: 'catalog',
      connectivity: 'wired',
    });
  }

  if (input.selectedProducts.cellularBackup) {
    const cellular = input.selectedProducts.cellularBackup;
    const unitPrice = getCatalogUnitPrice(cellular);
    pushBomLine(bomItems, nextLineId, {
      category: 'cellular_backup',
      vendor: cellular.vendor,
      model: cellular.model,
      quantity: 1,
      unitPrice,
      lineTotal: lineTotal(1, unitPrice),
      pricingBasis: cellular.pricingBasis,
      source: 'catalog',
      connectivity: 'cellular', // SIM-based, no local cable
    });
  }

  if (config.includeCabling && apQuantity > 0) {
    const cableType: CableType = (input.config as any)?.cableType || 'CAT6';
    const wiredDrops = apQuantity + switchQuantity;
    const floorArea = input.totalFloorAreaSqft ?? 0;
    const cableLengthMeters = estimateCableLengthMeters(floorArea, wiredDrops);

    let unitPrice: number | null;
    if (cableLengthMeters > 0) {
      // Area-based: price = total_meters × price_per_meter, then spread across drops
      const pricePerMeter = DEFAULT_CABLE_PRICE_PER_METER[cableType];
      const totalCableCost = cableLengthMeters * pricePerMeter;
      unitPrice = toMoneyOrNull(wiredDrops > 0 ? totalCableCost / wiredDrops : totalCableCost);
    } else {
      // Fallback: legacy per-drop pricing
      unitPrice = toMoneyOrNull(config.cablingCostPerDrop);
    }

    const cableLabel = cableLengthMeters > 0
      ? `${cableType} Cabling (${Math.round(cableLengthMeters)}m est.)`
      : `${cableType} Cabling`;

    pushBomLine(bomItems, nextLineId, {
      category: 'cabling',
      model: cableLabel,
      quantity: wiredDrops > 0 ? wiredDrops : apQuantity,
      unitPrice,
      lineTotal: lineTotal(wiredDrops > 0 ? wiredDrops : apQuantity, unitPrice),
      source: 'config',
      notes: cableLengthMeters > 0
        ? `${cableType} cable, ${cableLengthMeters}m total from ${floorArea} sqft floor area.`
        : `${cableType} cable, per-drop pricing.`,
      cableType,
      cableLengthMeters: cableLengthMeters > 0 ? cableLengthMeters : undefined,
      connectivity: 'wired',
    });
  }

  if (config.includeLabor && apQuantity > 0) {
    const effectiveUnitPrice = config.laborAsFlatItem
      ? toMoneyOrNull(config.installationFlat)
      : toMoneyOrNull(
        (config.laborHoursPerAp ?? 0) > 0 && (config.laborRate ?? 0) > 0
          ? (config.laborHoursPerAp as number) * (config.laborRate as number)
          : config.installationFlat,
      );

    pushBomLine(bomItems, nextLineId, {
      category: 'labor',
      model: config.laborAsFlatItem ? 'Installation labor (flat)' : 'Installation labor per AP',
      quantity: config.laborAsFlatItem ? 1 : apQuantity,
      unitPrice: effectiveUnitPrice,
      lineTotal: lineTotal(config.laborAsFlatItem ? 1 : apQuantity, effectiveUnitPrice),
      source: 'config',
      notes: config.laborAsFlatItem ? 'Flat installation placeholder line.' : undefined,
    });
  }

  if (config.includeUps && switchQuantity > 0) {
    const unitPrice = toMoneyOrNull(config.upsPrice);
    pushBomLine(bomItems, nextLineId, {
      category: 'ups',
      model: 'UPS Backup Power',
      quantity: switchQuantity,
      unitPrice,
      lineTotal: lineTotal(switchQuantity, unitPrice),
      source: 'placeholder',
      notes: 'Optional UPS placeholder line.',
    });
  }

  if (config.includeManagedServices) {
    const managedRows: Array<{ model: string; price: number | null }> = [
      { model: 'Managed installation coordination', price: toMoneyOrNull(config.installationFlat) },
      { model: 'Managed monitoring (monthly)', price: toMoneyOrNull(config.monitoringMonthly) },
      { model: 'Managed Wi-Fi support (monthly)', price: toMoneyOrNull(config.managedWifiMonthly) },
    ];

    for (const row of managedRows) {
      pushBomLine(bomItems, nextLineId, {
        category: 'managed_service',
        model: row.model,
        quantity: 1,
        unitPrice: row.price,
        lineTotal: lineTotal(1, row.price),
        source: 'placeholder',
      });
    }
    notes.push('Added managed services placeholders (installation, monitoring, support).');
  }

  return { bomItems, notes, warnings };
};

export const calculateBomTotals = (bomItems: BomItem[]): BomTotals => {
  const serviceCategories = new Set<BomItem['category']>(['license', 'cabling', 'labor', 'managed_service']);

  let hardwareSubtotal = 0;
  let servicesSubtotal = 0;
  let hasHardwareNull = false;
  let hasServicesNull = false;

  for (const item of bomItems) {
    const isService = serviceCategories.has(item.category);
    if (item.lineTotal === null) {
      if (isService) hasServicesNull = true;
      else hasHardwareNull = true;
      continue;
    }

    if (isService) servicesSubtotal += item.lineTotal;
    else hardwareSubtotal += item.lineTotal;
  }

  const hardware = hasHardwareNull ? null : Number(hardwareSubtotal.toFixed(2));
  const services = hasServicesNull ? null : Number(servicesSubtotal.toFixed(2));
  const grandTotal = hardware !== null && services !== null
    ? Number((hardware + services).toFixed(2))
    : null;

  return {
    hardwareSubtotal: hardware,
    servicesSubtotal: services,
    grandTotal,
  };
};

export const toBomBuilderConfig = (
  bomConfig: BomConfig | undefined,
  options: {
    includeCabling?: boolean;
    includeInstallation?: boolean;
    includeManagedServices?: boolean;
    includeUps?: boolean;
  },
): Partial<BomBuilderConfig> => {
  return {
    includeCabling: options.includeCabling,
    includeLabor: options.includeInstallation,
    includeManagedServices: options.includeManagedServices,
    includeUps: options.includeUps,
    licensePricePerAp: bomConfig?.licensePricePerAp,
    cablingCostPerDrop: bomConfig?.cablingCostPerDrop,
    laborHoursPerAp: bomConfig?.laborHoursPerAp,
    laborRate: bomConfig?.laborRate,
    installationFlat: bomConfig?.installationFlat,
    upsPrice: bomConfig?.upsPrice,
    managedWifiMonthly: bomConfig?.managedWifiMonthly,
    monitoringMonthly: bomConfig?.monitoringMonthly,
  };
};

