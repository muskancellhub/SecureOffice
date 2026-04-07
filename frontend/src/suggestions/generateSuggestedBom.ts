import { buildBomItems, calculateBomTotals } from './bomBuilder';
import { LocalInMemoryProductRetriever } from './retriever';
import { suggestProducts } from './suggestionEngine';
import type { ProductRetriever, ProductSuggestionInput, SuggestedBomOutput, Vendor } from './types';

const isPositiveInt = (value: number): boolean => Number.isFinite(value) && value > 0;

const resolveRecommendedApCount = (input: ProductSuggestionInput): number => {
  const byCounts = Number(input.calculatorResult.counts?.indoorAPsFinal || 0);
  if (isPositiveInt(byCounts)) return Math.floor(byCounts);

  const bySummary = Number(input.calculatorResult.summary?.recommendedIndoorAPs || 0);
  if (isPositiveInt(bySummary)) return Math.floor(bySummary);

  return 0;
};

const resolveRecommendedSwitchCount = (input: ProductSuggestionInput): number => {
  const byCounts = Number(input.calculatorResult.counts?.switchCount || 0);
  if (isPositiveInt(byCounts)) return Math.floor(byCounts);

  const bySummary = Number(input.calculatorResult.summary?.recommendedSwitches || 0);
  if (isPositiveInt(bySummary)) return Math.floor(bySummary);

  return 0;
};

const resolveVendorStrategyLabel = (
  preferredVendor: Vendor | 'auto' | undefined,
  preferSingleVendor: boolean | undefined,
  preferCheapest: boolean | undefined,
): string => {
  if (preferredVendor && preferredVendor !== 'auto') {
    return `preferred_vendor:${preferredVendor}`;
  }
  if (preferSingleVendor) {
    return 'single_vendor_preferred';
  }
  if (preferCheapest) {
    return 'cheapest_acceptable';
  }
  return 'balanced_auto';
};

export const validateSuggestionInput = (input: ProductSuggestionInput): string[] => {
  const warnings: string[] = [];

  if (!Array.isArray(input.catalog) || input.catalog.length === 0) {
    warnings.push('Catalog is empty; suggestions may fall back to placeholders.');
  }

  if (resolveRecommendedApCount(input) <= 0) {
    warnings.push('calculatorResult is missing a valid AP count (counts.indoorAPsFinal or summary.recommendedIndoorAPs).');
  }

  if (resolveRecommendedSwitchCount(input) <= 0) {
    warnings.push('calculatorResult is missing a valid switch count (counts.switchCount or summary.recommendedSwitches).');
  }

  return warnings;
};

export const generateSuggestedBom = (
  input: ProductSuggestionInput,
  retriever?: ProductRetriever,
): SuggestedBomOutput => {
  const baseWarnings = validateSuggestionInput(input);
  const effectiveRetriever = retriever || new LocalInMemoryProductRetriever(input.catalog);

  const suggestion = suggestProducts(effectiveRetriever, {
    calculatorResult: input.calculatorResult,
    businessContext: {
      indoorOutdoor: input.businessContext.indoorOutdoor,
      needsGateway: input.businessContext.needsGateway,
      needsCellularBackup: input.businessContext.needsCellularBackup,
    },
    selectionPreferences: input.selectionPreferences,
  });

  const bomResult = buildBomItems({
    calculatorResult: input.calculatorResult,
    selectedProducts: suggestion.selectedProducts,
    retriever: effectiveRetriever,
    config: {
      includeManagedServices: Boolean(input.businessContext.needsManagedServices),
    },
  });

  const totals = calculateBomTotals(bomResult.bomItems);
  const notes = [...suggestion.notes, ...bomResult.notes];
  const warnings = [...baseWarnings, ...suggestion.warnings, ...bomResult.warnings];

  return {
    retrievedCandidates: suggestion.retrievedCandidates,
    selectedProducts: suggestion.selectedProducts,
    bomItems: bomResult.bomItems,
    totals,
    summary: {
      recommendedIndoorAPs: Math.max(0, resolveRecommendedApCount(input)),
      selectedVendorStrategy: resolveVendorStrategyLabel(
        input.selectionPreferences?.preferredVendor,
        input.selectionPreferences?.preferSingleVendor,
        input.selectionPreferences?.preferCheapest,
      ),
      notes,
    },
    warnings,
  };
};

