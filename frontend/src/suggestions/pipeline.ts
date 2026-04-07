import { buildBomItems, calculateBomTotals, toBomBuilderConfig } from './bomBuilder';
import { topologyToDrawioXml } from './drawioGenerator';
import { buildMailboxOrderPayload } from './mailboxPayload';
import { buildPreviewPayload } from './previewPayload';
import { LocalInMemoryProductRetriever } from './retriever';
import { suggestProducts } from './suggestionEngine';
import { generateTopologyFromBom } from './topologyGenerator';
import { validatePipelineInput } from './validation';
import type { PipelineInput, PipelineOutput, SelectionPreferences, Vendor } from './types';

const resolveVendorStrategyLabel = (selectionPreferences: SelectionPreferences | undefined): string => {
  const preferred = selectionPreferences?.preferredVendor;
  if (preferred && preferred !== 'auto') {
    return `preferred_vendor:${preferred}`;
  }
  if (selectionPreferences?.preferSingleVendor) {
    return 'single_vendor_preferred';
  }
  if (selectionPreferences?.preferCheapest) {
    return 'cheapest_acceptable';
  }
  return 'balanced_auto';
};

const resolvePreferredVendor = (
  preferredVendor: Vendor | 'auto' | undefined,
  preferSingleVendor: boolean | undefined,
  selectedProducts: PipelineOutput['selectedProducts'],
): Vendor | undefined => {
  if (preferredVendor && preferredVendor !== 'auto') return preferredVendor;
  if (!preferSingleVendor) return undefined;

  const vendorCounts = new Map<Vendor, number>();
  const items = [selectedProducts.ap, selectedProducts.switch, selectedProducts.gateway, selectedProducts.cellularBackup];
  for (const item of items) {
    if (!item?.vendor) continue;
    vendorCounts.set(item.vendor, (vendorCounts.get(item.vendor) || 0) + 1);
  }

  let winner: Vendor | undefined;
  let max = 0;
  for (const [vendor, count] of vendorCounts) {
    if (count > max) {
      max = count;
      winner = vendor;
    }
  }
  return winner;
};

export const generateConfigurationPreviewAndOrderPayload = (input: PipelineInput): PipelineOutput => {
  const warnings = validatePipelineInput(input);
  const retriever = new LocalInMemoryProductRetriever(input.catalog);

  const suggestion = suggestProducts(retriever, {
    calculatorResult: input.calculatorResult,
    businessContext: {
      indoorOutdoor: input.businessContext.indoorOutdoor,
      needsGateway: input.includeGateway ?? input.businessContext.needsGateway,
      needsCellularBackup: input.includeCellularBackup ?? input.businessContext.needsCellularBackup,
    },
    selectionPreferences: input.selectionPreferences,
  });

  const bomResult = buildBomItems({
    calculatorResult: input.calculatorResult,
    selectedProducts: suggestion.selectedProducts,
    retriever,
    config: toBomBuilderConfig(input.bomConfig, {
      includeCabling: input.includeCabling ?? true,
      includeInstallation: input.includeInstallation ?? true,
      includeManagedServices: input.includeManagedServices ?? input.businessContext.needsManagedServices,
      includeUps: input.includeUps ?? false,
    }),
  });

  const totals = calculateBomTotals(bomResult.bomItems);
  const topologyResult = generateTopologyFromBom({
    bomItems: bomResult.bomItems,
    businessContext: input.businessContext,
  });
  const drawio = topologyToDrawioXml(topologyResult.topology);

  const selectedVendorStrategy = resolveVendorStrategyLabel(input.selectionPreferences);
  const selectedProducts = {
    ap: suggestion.selectedProducts.ap,
    switch: suggestion.selectedProducts.switch,
    gateway: suggestion.selectedProducts.gateway,
    cellularBackup: suggestion.selectedProducts.cellularBackup,
  };

  const finalNotes = [
    ...suggestion.notes,
    ...bomResult.notes,
    ...topologyResult.assumptions,
  ];

  const preferredVendorFromSelection = resolvePreferredVendor(
    input.selectionPreferences?.preferredVendor,
    input.selectionPreferences?.preferSingleVendor,
    selectedProducts,
  );
  if (preferredVendorFromSelection && input.selectionPreferences?.preferSingleVendor) {
    finalNotes.push(`Single-vendor preference favored ${preferredVendorFromSelection} where possible.`);
  }

  const previewPayload = buildPreviewPayload({
    calculatorResult: input.calculatorResult,
    selectedProducts: suggestion.selectedProducts,
    bomItems: bomResult.bomItems,
    totals,
    topology: topologyResult.topology,
    drawio,
    selectedVendorStrategy,
    notes: finalNotes,
  });

  const mailboxPayload = buildMailboxOrderPayload({
    customer: input.customer,
    calculatorResult: input.calculatorResult,
    selectedProducts: suggestion.selectedProducts,
    bomItems: bomResult.bomItems,
    totals,
    topology: topologyResult.topology,
    drawioXml: drawio.xml,
    warnings: [...warnings, ...suggestion.warnings, ...bomResult.warnings, ...topologyResult.assumptions],
  });

  return {
    retrievedCandidates: suggestion.retrievedCandidates,
    selectedProducts,
    bomItems: bomResult.bomItems,
    topology: topologyResult.topology,
    drawio,
    previewPayload,
    mailboxPayload,
    warnings: [
      ...warnings,
      ...suggestion.warnings,
      ...bomResult.warnings,
      ...topologyResult.assumptions,
    ],
  };
};

