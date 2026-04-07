import { describe, expect, test } from 'vitest';

import { buildBomItems, calculateBomTotals } from '../bomBuilder';
import { topologyToDrawioXml } from '../drawioGenerator';
import { buildMailboxOrderPayload } from '../mailboxPayload';
import { generateConfigurationPreviewAndOrderPayload } from '../pipeline';
import { buildPreviewPayload } from '../previewPayload';
import { LocalInMemoryProductRetriever } from '../retriever';
import {
  suggestAccessPoint,
  suggestCellularBackup,
  suggestGateway,
  suggestSwitch,
} from '../suggestionEngine';
import { generateTopologyFromBom } from '../topologyGenerator';
import type { CatalogItem, PipelineInput, SelectedProducts } from '../types';

const catalogFixture: CatalogItem[] = [
  {
    vendor: 'Meraki',
    model: 'MR44',
    category: 'wifi_ap',
    wifiStandard: 'wifi6',
    indoorOutdoor: 'indoor',
    smbFit: true,
    price: 899,
    pricingBasis: 'public',
  },
  {
    vendor: 'InHand',
    model: 'AP900',
    category: 'wifi_ap',
    wifiStandard: 'wifi6',
    indoorOutdoor: 'indoor',
    smbFit: true,
    price: 499,
    pricingBasis: 'street',
  },
  {
    vendor: 'Extreme Networks',
    model: 'AP305C',
    category: 'wifi_ap',
    wifiStandard: 'wifi6e',
    indoorOutdoor: 'both',
    smbFit: true,
    price: 650,
    pricingBasis: 'public',
  },
  {
    vendor: 'Meraki',
    model: 'MS120-24P',
    category: 'switch',
    poe: true,
    ports: 24,
    smbFit: true,
    price: 1299,
    pricingBasis: 'street',
  },
  {
    vendor: 'SkyMirr',
    model: 'SM-SW8P',
    category: 'switch',
    poe: true,
    ports: 8,
    smbFit: true,
    price: 399,
    pricingBasis: 'public',
  },
  {
    vendor: 'Meraki',
    model: 'MX75',
    category: 'firewall',
    smbFit: true,
    price: 1199,
    pricingBasis: 'public',
  },
  {
    vendor: 'Extreme Networks',
    model: 'GW500',
    category: 'gateway',
    smbFit: true,
    price: 999,
    pricingBasis: 'street',
  },
  {
    vendor: 'InHand',
    model: 'IR302',
    category: 'cellular_gateway',
    smbFit: true,
    price: 499,
    pricingBasis: 'public',
  },
  {
    vendor: 'SkyMirr',
    model: 'SM-CELL10',
    category: 'router',
    smbFit: true,
    price: 459,
    pricingBasis: 'public',
  },
  {
    vendor: 'Meraki',
    model: 'LIC-ENT',
    category: 'license',
    price: 120,
    pricingBasis: 'public',
  },
];

const calculatorFixture = {
  summary: { recommendedIndoorAPs: 6, recommendedSwitches: 1 },
  counts: { indoorAPsFinal: 6, switchCount: 1 },
  inputsNormalized: { wifiStandard: 'wifi6' as const },
};

const makeSelectedProducts = (): SelectedProducts => ({
  ap: catalogFixture.find((item) => item.model === 'MR44'),
  switch: catalogFixture.find((item) => item.model === 'MS120-24P'),
  gateway: catalogFixture.find((item) => item.model === 'MX75'),
  cellularBackup: catalogFixture.find((item) => item.model === 'IR302'),
});

describe('suggestion engine', () => {
  test('AP selection respects preferred vendor', () => {
    const retriever = new LocalInMemoryProductRetriever(catalogFixture);
    const result = suggestAccessPoint(retriever, {
      preferredVendor: 'Meraki',
      targetWifiStandard: 'wifi6',
      indoorOutdoor: 'indoor',
      preferCheapest: false,
    });

    expect(result.selected?.vendor).toBe('Meraki');
    expect(result.selected?.model).toBe('MR44');
  });

  test('AP selection picks cheapest acceptable candidate when preferCheapest=true', () => {
    const retriever = new LocalInMemoryProductRetriever(catalogFixture);
    const result = suggestAccessPoint(retriever, {
      targetWifiStandard: 'wifi6',
      indoorOutdoor: 'indoor',
      preferCheapest: true,
    });

    expect(result.selected?.vendor).toBe('InHand');
    expect(result.selected?.model).toBe('AP900');
  });

  test('switch selection adjusts quantity when port count is too small', () => {
    const retriever = new LocalInMemoryProductRetriever(catalogFixture);
    const result = suggestSwitch(retriever, {
      requiredApCount: 20,
      calculatorSwitchCount: 1,
      preferredVendor: 'SkyMirr',
      preferCheapest: true,
    });

    expect(result.selected?.model).toBe('SM-SW8P');
    expect(result.quantity).toBe(3);
  });

  test('gateway selection returns gateway/firewall candidate when enabled', () => {
    const retriever = new LocalInMemoryProductRetriever(catalogFixture);
    const result = suggestGateway(retriever, {
      enabled: true,
      preferredVendor: 'Extreme Networks',
      preferCheapest: false,
    });

    expect(result.selected).toBeDefined();
    expect(['gateway', 'firewall', 'security_appliance']).toContain(result.selected?.category);
  });

  test('cellular backup selection prefers InHand/SkyMirr family when available', () => {
    const retriever = new LocalInMemoryProductRetriever(catalogFixture);
    const result = suggestCellularBackup(retriever, {
      enabled: true,
      preferCheapest: false,
    });

    expect(result.selected).toBeDefined();
    expect(['InHand', 'SkyMirr']).toContain(result.selected?.vendor);
  });
});

describe('bom builder and totals', () => {
  test('BOM generation uses calculator quantities and includes ids', () => {
    const retriever = new LocalInMemoryProductRetriever(catalogFixture);
    const result = buildBomItems({
      calculatorResult: calculatorFixture,
      selectedProducts: makeSelectedProducts(),
      retriever,
      config: {
        includeManagedServices: true,
      },
    });

    const apLine = result.bomItems.find((line) => line.category === 'wifi_ap');
    const switchLine = result.bomItems.find((line) => line.category === 'switch');
    const licenseLine = result.bomItems.find((line) => line.category === 'license');
    const managedRows = result.bomItems.filter((line) => line.category === 'managed_service');

    expect(apLine?.quantity).toBe(6);
    expect(switchLine?.quantity).toBe(1);
    expect(licenseLine?.quantity).toBe(6);
    expect(managedRows.length).toBe(3);
    expect(result.bomItems.every((line) => line.id.startsWith('line-'))).toBe(true);
  });

  test('totals calculation splits hardware/services and computes grand total', () => {
    const totals = calculateBomTotals([
      {
        id: 'line-1',
        category: 'wifi_ap',
        model: 'AP',
        quantity: 2,
        unitPrice: 100,
        lineTotal: 200,
        source: 'catalog',
      },
      {
        id: 'line-2',
        category: 'labor',
        model: 'Labor',
        quantity: 1,
        unitPrice: 150,
        lineTotal: 150,
        source: 'config',
      },
    ]);

    expect(totals.hardwareSubtotal).toBe(200);
    expect(totals.servicesSubtotal).toBe(150);
    expect(totals.grandTotal).toBe(350);
  });
});

describe('topology + drawio + payloads', () => {
  test('topology generation creates internet->gateway->switch->ap path and grouped AP quantity', () => {
    const bom = buildBomItems({
      calculatorResult: {
        summary: { recommendedIndoorAPs: 4, recommendedSwitches: 1 },
        counts: { indoorAPsFinal: 4, switchCount: 1 },
      },
      selectedProducts: makeSelectedProducts(),
      retriever: new LocalInMemoryProductRetriever(catalogFixture),
    }).bomItems;

    const topologyResult = generateTopologyFromBom({
      bomItems: bom,
      businessContext: { useCases: ['cameras', 'sensors'] },
    });

    const apNode = topologyResult.topology.nodes.find((node) => node.type === 'wifi_ap');
    const hasGatewayEdge = topologyResult.topology.edges.some((edge) => edge.source === 'internet' && edge.target === 'gateway');
    const hasSwitchApEdge = topologyResult.topology.edges.some((edge) => edge.source === 'switch' && edge.target === 'wifi-ap');

    expect(hasGatewayEdge).toBe(true);
    expect(hasSwitchApEdge).toBe(true);
    expect(apNode?.quantity).toBe(4);
  });

  test('draw.io XML generation is stable and references expected labels', () => {
    const topology = generateTopologyFromBom({
      bomItems: buildBomItems({
        calculatorResult: calculatorFixture,
        selectedProducts: makeSelectedProducts(),
      }).bomItems,
      businessContext: { useCases: ['pos', 'camera'] },
    }).topology;

    const xmlA = topologyToDrawioXml(topology);
    const xmlB = topologyToDrawioXml(topology);

    expect(xmlA.xml.length).toBeGreaterThan(0);
    expect(xmlA.xml).toContain('Internet / WAN');
    expect(xmlA.xml).toContain('PoE Switch Layer');
    expect(xmlA.xml).toContain('edge-switch-ap');
    expect(xmlA.xml).toBe(xmlB.xml);
  });

  test('topology falls back to internet->switch path when no gateway exists', () => {
    const selectedWithoutGateway: SelectedProducts = {
      ap: catalogFixture.find((item) => item.model === 'MR44'),
      switch: catalogFixture.find((item) => item.model === 'MS120-24P'),
    };

    const bomItems = buildBomItems({
      calculatorResult: calculatorFixture,
      selectedProducts: selectedWithoutGateway,
      retriever: new LocalInMemoryProductRetriever(catalogFixture),
    }).bomItems;

    const topologyResult = generateTopologyFromBom({
      bomItems,
      businessContext: {},
    });

    const hasInternetSwitch = topologyResult.topology.edges.some((edge) => edge.source === 'internet' && edge.target === 'switch');
    const hasGatewayNode = topologyResult.topology.nodes.some((node) => node.id === 'gateway');

    expect(hasInternetSwitch).toBe(true);
    expect(hasGatewayNode).toBe(false);
    expect(topologyResult.assumptions.some((assumption) => assumption.includes('direct-to-switch'))).toBe(true);
  });

  test('preview payload and mailbox payload include expected sections', () => {
    const bomItems = buildBomItems({
      calculatorResult: calculatorFixture,
      selectedProducts: makeSelectedProducts(),
      retriever: new LocalInMemoryProductRetriever(catalogFixture),
    }).bomItems;
    const totals = calculateBomTotals(bomItems);
    const topologyResult = generateTopologyFromBom({ bomItems, businessContext: { needsManagedServices: true } });
    const drawio = topologyToDrawioXml(topologyResult.topology);

    const previewPayload = buildPreviewPayload({
      calculatorResult: calculatorFixture,
      selectedProducts: makeSelectedProducts(),
      bomItems,
      totals,
      topology: topologyResult.topology,
      drawio,
      selectedVendorStrategy: 'balanced_auto',
      notes: ['Preview note'],
    });

    const mailboxPayload = buildMailboxOrderPayload({
      customer: { customerName: 'Alex', companyName: 'Bluebird' },
      calculatorResult: calculatorFixture,
      selectedProducts: makeSelectedProducts(),
      bomItems,
      totals,
      topology: topologyResult.topology,
      drawioXml: drawio.xml,
      warnings: ['Pricing is estimate-level'],
    });

    expect(previewPayload.summary.recommendedIndoorAPs).toBe(6);
    expect(previewPayload.drawio.meta.nodeCount).toBe(topologyResult.topology.nodes.length);
    expect(mailboxPayload.fulfillmentNotes.length).toBeGreaterThan(4);
    expect(mailboxPayload.drawioXml).toContain('<mxfile');
  });
});

describe('full pipeline', () => {
  test('end-to-end pipeline returns candidates, BOM, topology, drawio, preview, and mailbox payload', () => {
    const input: PipelineInput = {
      calculatorResult: calculatorFixture,
      businessContext: {
        businessType: 'retail',
        environmentType: 'office',
        indoorOutdoor: 'indoor',
        useCases: ['pos', 'camera', 'signage'],
        needsManagedServices: true,
        needsGateway: true,
        needsCellularBackup: true,
      },
      selectionPreferences: {
        preferredVendor: 'auto',
        preferCheapest: false,
        preferSingleVendor: false,
      },
      bomConfig: {
        installationFlat: 500,
      },
      catalog: catalogFixture,
      customer: {
        customerName: 'Alex Rivera',
        companyName: 'Bluebird Cafe Group',
        email: 'alex@example.com',
      },
      includeGateway: true,
      includeCellularBackup: true,
      includeCabling: true,
      includeInstallation: true,
      includeManagedServices: true,
      includeUps: true,
    };

    const output = generateConfigurationPreviewAndOrderPayload(input);

    expect(output.retrievedCandidates.aps.length).toBeGreaterThan(0);
    expect(output.selectedProducts.ap).toBeDefined();
    expect(output.bomItems.length).toBeGreaterThan(0);
    expect(output.topology.nodes.length).toBeGreaterThan(0);
    expect(output.drawio.xml).toContain('<mxfile');
    expect(output.previewPayload.bomItems.length).toBe(output.bomItems.length);
    expect(output.mailboxPayload.bomItems.length).toBe(output.bomItems.length);
    expect(output.mailboxPayload.fulfillmentNotes.length).toBeGreaterThan(0);
  });
});
