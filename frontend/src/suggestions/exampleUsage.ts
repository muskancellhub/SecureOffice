import { generateConfigurationPreviewAndOrderPayload } from './pipeline';
import type { CatalogItem, PipelineInput } from './types';

export const demoCatalogSample: CatalogItem[] = [
  {
    vendor: 'Meraki',
    model: 'MR44',
    category: 'wifi_ap',
    price: 899,
    pricingBasis: 'public',
    wifiStandard: 'wifi6',
    indoorOutdoor: 'indoor',
    smbFit: true,
  },
  {
    vendor: 'InHand',
    model: 'AP900',
    category: 'wifi_ap',
    price: 499,
    pricingBasis: 'street',
    wifiStandard: 'wifi6',
    indoorOutdoor: 'indoor',
    smbFit: true,
  },
  {
    vendor: 'Extreme Networks',
    model: 'X440-G2-24p',
    category: 'switch',
    price: 1499,
    pricingBasis: 'street',
    ports: 24,
    poe: true,
    smbFit: true,
  },
  {
    vendor: 'Meraki',
    model: 'MS120-24P',
    category: 'switch',
    price: 1299,
    pricingBasis: 'public',
    ports: 24,
    poe: true,
    smbFit: true,
  },
  {
    vendor: 'Meraki',
    model: 'MX75',
    category: 'firewall',
    price: 1199,
    pricingBasis: 'public',
    smbFit: true,
  },
  {
    vendor: 'InHand',
    model: 'IR302',
    category: 'cellular_gateway',
    price: 499,
    pricingBasis: 'public',
    smbFit: true,
  },
  {
    vendor: 'Meraki',
    model: 'LIC-ENT',
    category: 'license',
    price: 119,
    pricingBasis: 'public',
  },
];

export const demoPipelineInput: PipelineInput = {
  calculatorResult: {
    summary: {
      recommendedIndoorAPs: 8,
      recommendedSwitches: 1,
    },
    counts: {
      indoorAPsFinal: 8,
      switchCount: 1,
    },
    inputsNormalized: {
      wifiStandard: 'wifi6',
      businessType: 'retail',
      environmentType: 'office',
      totalUsers: 75,
    },
  },
  businessContext: {
    businessType: 'retail',
    environmentType: 'office',
    indoorOutdoor: 'indoor',
    useCases: ['pos', 'camera'],
    needsManagedServices: true,
    needsGateway: true,
    needsCellularBackup: true,
  },
  selectionPreferences: {
    preferredVendor: 'auto',
    preferCheapest: false,
    preferSingleVendor: true,
  },
  bomConfig: {
    licensePricePerAp: 119,
    cablingCostPerDrop: 180,
    laborHoursPerAp: 2,
    laborRate: 95,
    monitoringMonthly: 99,
    managedWifiMonthly: 149,
    installationFlat: 500,
  },
  catalog: demoCatalogSample,
  includeGateway: true,
  includeCellularBackup: true,
  includeCabling: true,
  includeInstallation: true,
  includeManagedServices: true,
  includeUps: false,
  customer: {
    customerName: 'Alex Rivera',
    companyName: 'Bluebird Cafe Group',
    email: 'alex@bluebird.example',
    phone: '+1-212-555-0135',
    locationName: 'Midtown NYC',
  },
};

export const demoPipelineOutput = (): ReturnType<typeof generateConfigurationPreviewAndOrderPayload> => {
  return generateConfigurationPreviewAndOrderPayload(demoPipelineInput);
};

