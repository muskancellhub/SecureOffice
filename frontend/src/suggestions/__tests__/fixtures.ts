import type { CalculatorResult, CatalogItem } from '../types';

/** Multi-vendor catalog covering AP/switch/firewall/gateway/cellular/license. */
export const catalogFixture: CatalogItem[] = [
  { vendor: 'Meraki', model: 'MR44', category: 'wifi_ap', wifiStandard: 'wifi6', indoorOutdoor: 'indoor', smbFit: true, price: 899, pricingBasis: 'public' },
  { vendor: 'InHand', model: 'AP900', category: 'wifi_ap', wifiStandard: 'wifi6', indoorOutdoor: 'indoor', smbFit: true, price: 499, pricingBasis: 'street' },
  { vendor: 'Extreme Networks', model: 'AP305C', category: 'wifi_ap', wifiStandard: 'wifi6e', indoorOutdoor: 'both', smbFit: true, price: 650, pricingBasis: 'public' },
  { vendor: 'Meraki', model: 'MS120-24P', category: 'switch', poe: true, ports: 24, smbFit: true, price: 1299, pricingBasis: 'street' },
  { vendor: 'SkyMirr', model: 'SM-SW8P', category: 'switch', poe: true, ports: 8, smbFit: true, price: 399, pricingBasis: 'public' },
  { vendor: 'Meraki', model: 'MX75', category: 'firewall', smbFit: true, price: 1199, pricingBasis: 'public' },
  { vendor: 'Extreme Networks', model: 'GW500', category: 'gateway', smbFit: true, price: 999, pricingBasis: 'street' },
  { vendor: 'InHand', model: 'IR302', category: 'cellular_gateway', smbFit: true, price: 499, pricingBasis: 'public' },
  { vendor: 'SkyMirr', model: 'SM-CELL10', category: 'router', smbFit: true, price: 459, pricingBasis: 'public' },
  { vendor: 'Meraki', model: 'LIC-ENT', category: 'license', price: 120, pricingBasis: 'public' },
];

export const calculatorFixture: CalculatorResult = {
  summary: { recommendedIndoorAPs: 6, recommendedSwitches: 1 },
  counts: { indoorAPsFinal: 6, switchCount: 1 },
  inputsNormalized: { wifiStandard: 'wifi6' as const },
};
