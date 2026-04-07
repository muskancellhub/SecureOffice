import type { CatalogItem, PipelineInput } from './types';

const isFiniteNumber = (value: unknown): value is number => {
  return typeof value === 'number' && Number.isFinite(value);
};

const hasValidPositiveCount = (value: unknown): boolean => {
  return isFiniteNumber(value) && value > 0;
};

const validateCatalogPrice = (item: CatalogItem): string | null => {
  if (item.price === undefined || item.price === null) return null;
  if (!isFiniteNumber(item.price) || item.price < 0) {
    return `Catalog item ${item.vendor} ${item.model} has invalid price value.`;
  }
  return null;
};

export const validatePipelineInput = (input: PipelineInput): string[] => {
  const warnings: string[] = [];

  if (!Array.isArray(input.catalog) || input.catalog.length === 0) {
    warnings.push('Catalog is empty; product selection will likely fall back to placeholders.');
  }

  if (!hasValidPositiveCount(input.calculatorResult.counts?.indoorAPsFinal) &&
      !hasValidPositiveCount(input.calculatorResult.summary?.recommendedIndoorAPs)) {
    warnings.push('Missing calculator AP count (counts.indoorAPsFinal or summary.recommendedIndoorAPs).');
  }

  if (!hasValidPositiveCount(input.calculatorResult.counts?.switchCount) &&
      !hasValidPositiveCount(input.calculatorResult.summary?.recommendedSwitches)) {
    warnings.push('Missing calculator switch count (counts.switchCount or summary.recommendedSwitches).');
  }

  if (isFiniteNumber(input.calculatorResult.counts?.indoorAPsFinal) && input.calculatorResult.counts.indoorAPsFinal < 0) {
    warnings.push('Calculator AP count is negative; values should be non-negative.');
  }
  if (isFiniteNumber(input.calculatorResult.counts?.switchCount) && input.calculatorResult.counts.switchCount < 0) {
    warnings.push('Calculator switch count is negative; values should be non-negative.');
  }

  for (const item of input.catalog) {
    const maybeWarning = validateCatalogPrice(item);
    if (maybeWarning) warnings.push(maybeWarning);
  }

  return warnings;
};

