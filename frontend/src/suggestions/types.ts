export type Vendor = 'Meraki' | 'Extreme Networks' | 'SkyMirr' | 'InHand';

export type WifiStandard = 'wifi5' | 'wifi6' | 'wifi6e' | 'wifi7';

export type IndoorOutdoor = 'indoor' | 'outdoor' | 'both';

export type CatalogCategory =
  | 'wifi_ap'
  | 'switch'
  | 'gateway'
  | 'firewall'
  | 'security_appliance'
  | 'cellular_gateway'
  | 'router'
  | 'license'
  | 'managed_service'
  | 'sensor'
  | 'camera'
  | 'other';

export type PricingBasis = 'public' | 'street' | 'quote_only' | 'unknown';

export type CatalogItem = {
  vendor: Vendor;
  model: string;
  family?: string;
  category: CatalogCategory;
  price?: number | null;
  pricingBasis?: PricingBasis;
  notes?: string;
  wifiStandard?: WifiStandard;
  ports?: number;
  poe?: boolean;
  managed?: boolean;
  indoorOutdoor?: IndoorOutdoor;
  smbFit?: boolean;
};

export type CalculatorResult = {
  summary: {
    recommendedIndoorAPs: number;
    recommendedSwitches: number;
    estimatedCapEx?: number;
  };
  counts: {
    indoorAPsFinal: number;
    switchCount: number;
  };
  inputsNormalized?: {
    wifiStandard?: WifiStandard;
    redundancyEnabled?: boolean;
    totalFloorAreaSqft?: number;
    businessType?: string;
    environmentType?: string;
    totalUsers?: number;
  };
};

export interface ProductQuery {
  query?: string;
  categories?: CatalogCategory[];
  vendors?: Vendor[];
  wifiStandard?: WifiStandard;
  indoorOutdoor?: IndoorOutdoor;
  smbOnly?: boolean;
  limit?: number;
}

export interface ProductRetriever {
  retrieveProducts(input: ProductQuery): CatalogItem[];
}

export type BusinessContext = {
  businessType?: string;
  environmentType?: string;
  useCases?: string[];
  indoorOutdoor?: 'indoor' | 'outdoor' | 'mixed';
  needsGuestWifi?: boolean;
  needsManagedServices?: boolean;
  needsCellularBackup?: boolean;
  needsGateway?: boolean;
  /** Office floor area in sqft — used for cable length estimation */
  totalFloorAreaSqft?: number;
};

export type SelectionPreferences = {
  preferredVendor?: Vendor | 'auto';
  allowedVendors?: Vendor[];
  preferCheapest?: boolean;
  preferSingleVendor?: boolean;
};

export type ProductSuggestionInput = {
  calculatorResult: CalculatorResult;
  businessContext: BusinessContext;
  selectionPreferences?: SelectionPreferences;
  catalog: CatalogItem[];
};

export type RetrievedCandidates = {
  aps: CatalogItem[];
  switches: CatalogItem[];
  gateways: CatalogItem[];
  cellular: CatalogItem[];
};

export type SelectedProducts = {
  ap?: CatalogItem;
  switch?: CatalogItem;
  switchQuantityOverride?: number;
  gateway?: CatalogItem;
  cellularBackup?: CatalogItem;
};

export type CableType = 'CAT5' | 'CAT6' | 'CAT6e';

/**
 * Connectivity classification for BOM items.
 * - 'wired'    → device requires a physical CAT cable run (routers, switches, AP uplinks, PoE cameras)
 * - 'wireless' → device connects over Wi-Fi (iPads, tablets, wireless endpoints)
 * - 'cellular' → device has its own SIM / 5G connectivity (cellular gateways, MiFi)
 * - 'na'       → not a connectable device (licenses, labor, services)
 */
export type ConnectivityType = 'wired' | 'wireless' | 'cellular' | 'na';

export type BomItemCategory =
  | 'wifi_ap'
  | 'license'
  | 'switch'
  | 'gateway'
  | 'cellular_backup'
  | 'cabling'
  | 'labor'
  | 'ups'
  | 'managed_service';

export type BomItem = {
  id: string;
  category: BomItemCategory;
  vendor?: string;
  model: string;
  quantity: number;
  unitPrice: number | null;
  lineTotal: number | null;
  pricingBasis?: string;
  source: 'catalog' | 'config' | 'placeholder';
  notes?: string;
  /** Connectivity classification — drives cable inclusion logic */
  connectivity?: ConnectivityType;
  /** For cabling lines: specific cable standard used */
  cableType?: CableType;
  /** For cabling lines: total estimated cable length in meters */
  cableLengthMeters?: number;
};

export type CablePricing = {
  /** Price per meter for each cable standard */
  CAT5: number;
  CAT6: number;
  CAT6e: number;
};

export type BomConfig = {
  licensePricePerAp?: number;
  cablingCostPerDrop?: number;
  /** Cable standard to use (defaults to CAT6) */
  cableType?: CableType;
  /** Per-meter pricing by cable standard */
  cablePricing?: CablePricing;
  laborHoursPerAp?: number;
  laborRate?: number;
  upsPrice?: number;
  managedWifiMonthly?: number;
  monitoringMonthly?: number;
  installationFlat?: number;
};

export type BomTotals = {
  hardwareSubtotal: number | null;
  servicesSubtotal: number | null;
  grandTotal: number | null;
};

export type TopologyNodeType =
  | 'internet'
  | 'gateway'
  | 'switch'
  | 'wifi_ap'
  | 'cellular_backup'
  | 'managed_service'
  | 'camera'
  | 'iot'
  | 'pos'
  | 'signage'
  | 'label';

export type TopologyNode = {
  id: string;
  type: TopologyNodeType;
  label: string;
  vendor?: string;
  model?: string;
  quantity?: number;
  iconKey?: string;
};

export type TopologyEdgeKind = 'wired' | 'wireless' | 'managed' | 'wan' | 'failover';

export type TopologyEdge = {
  id: string;
  source: string;
  target: string;
  label?: string;
  /** Connection type — drives visual styling and UX labeling */
  kind?: TopologyEdgeKind;
};

export type TopologyDiagram = {
  title: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  layoutHints?: {
    direction?: 'left_to_right' | 'top_to_bottom';
  };
};

export type DrawioOutput = {
  xml: string;
  meta: {
    nodeCount: number;
    edgeCount: number;
  };
};

export type PreviewPayload = {
  summary: {
    recommendedIndoorAPs: number;
    selectedVendorStrategy: string;
    estimatedHardwareSubtotal: number | null;
    estimatedServicesSubtotal: number | null;
    estimatedGrandTotal: number | null;
  };
  selectedProducts: {
    ap?: CatalogItem;
    switch?: CatalogItem;
    gateway?: CatalogItem;
    cellularBackup?: CatalogItem;
  };
  bomItems: BomItem[];
  topology: TopologyDiagram;
  drawio: DrawioOutput;
  notes: string[];
};

export type CustomerContext = {
  customerName?: string;
  companyName?: string;
  email?: string;
  phone?: string;
  notes?: string;
  locationName?: string;
};

export type MailboxOrderPayload = {
  customer: CustomerContext;
  calculatorResult: CalculatorResult;
  selectedProducts: {
    ap?: CatalogItem;
    switch?: CatalogItem;
    gateway?: CatalogItem;
    cellularBackup?: CatalogItem;
  };
  bomItems: BomItem[];
  totals: BomTotals;
  topology: TopologyDiagram;
  drawioXml: string;
  fulfillmentNotes: string[];
};

export type PipelineInput = {
  calculatorResult: CalculatorResult;
  businessContext: BusinessContext;
  selectionPreferences?: SelectionPreferences;
  bomConfig?: BomConfig;
  catalog: CatalogItem[];
  customer?: CustomerContext;
  includeGateway?: boolean;
  includeCellularBackup?: boolean;
  includeUps?: boolean;
  includeCabling?: boolean;
  includeInstallation?: boolean;
  includeManagedServices?: boolean;
};

export type PipelineOutput = {
  retrievedCandidates: RetrievedCandidates;
  selectedProducts: {
    ap?: CatalogItem;
    switch?: CatalogItem;
    gateway?: CatalogItem;
    cellularBackup?: CatalogItem;
  };
  bomItems: BomItem[];
  topology: TopologyDiagram;
  drawio: DrawioOutput;
  previewPayload: PreviewPayload;
  mailboxPayload: MailboxOrderPayload;
  warnings: string[];
};

export type SuggestedBomOutput = {
  retrievedCandidates: RetrievedCandidates;
  selectedProducts: SelectedProducts;
  bomItems: BomItem[];
  totals: BomTotals;
  summary: {
    recommendedIndoorAPs: number;
    selectedVendorStrategy: string;
    notes: string[];
  };
  warnings: string[];
};
