import { describe, expect, test } from 'vitest';

import { generateSuggestedBom, validateSuggestionInput } from '../generateSuggestedBom';
import type { CatalogItem, ProductQuery, ProductSuggestionInput } from '../types';
import { calculatorFixture, catalogFixture, partialCalculatorResult } from './fixtures';

const makeInput = (overrides: Partial<ProductSuggestionInput> = {}): ProductSuggestionInput => ({
  calculatorResult: calculatorFixture,
  businessContext: { indoorOutdoor: 'indoor', needsGateway: true, needsCellularBackup: false },
  catalog: catalogFixture,
  ...overrides,
});

describe('generateSuggestedBom', () => {
  test('happy path resolves counts, strategy, and consistent totals', () => {
    const out = generateSuggestedBom(makeInput());
    expect(out.summary.recommendedIndoorAPs).toBe(6);
    expect(out.summary.selectedVendorStrategy).toBe('balanced_auto');
    expect(out.bomItems.length).toBeGreaterThan(0);
    const lineSum = out.bomItems.reduce((acc, i) => acc + (i.lineTotal ?? 0), 0);
    expect(out.totals.grandTotal).toBeCloseTo(lineSum, 2);
  });

  test('falls back to summary counts and floors non-integers', () => {
    const out = generateSuggestedBom(makeInput({
      calculatorResult: partialCalculatorResult({
        summary: { recommendedIndoorAPs: 4.9, recommendedSwitches: 2.2 },
      }),
    }));
    expect(out.summary.recommendedIndoorAPs).toBe(4);
  });

  test('invalid input collects all validateSuggestionInput warnings', () => {
    const warnings = validateSuggestionInput(makeInput({
      catalog: [],
      calculatorResult: partialCalculatorResult(),
    }));
    expect(warnings).toHaveLength(3);
    expect(warnings[0]).toContain('Catalog is empty');
    expect(warnings[1]).toContain('AP count');
    expect(warnings[2]).toContain('switch count');
  });

  test('both count sources invalid -> 0 APs and warnings carried into output', () => {
    const out = generateSuggestedBom(makeInput({
      calculatorResult: partialCalculatorResult(),
    }));
    expect(out.summary.recommendedIndoorAPs).toBe(0);
    expect(out.warnings.some((w) => w.includes('AP count'))).toBe(true);
  });

  test('injected retriever is used instead of the local one', () => {
    const calls: ProductQuery[] = [];
    const stub = {
      retrieveProducts: (q: ProductQuery): CatalogItem[] => {
        calls.push(q);
        return catalogFixture.filter((i) => q.categories?.includes(i.category));
      },
    };
    const out = generateSuggestedBom(makeInput(), stub);
    expect(calls.length).toBeGreaterThan(0);
    expect(out.selectedProducts.ap).toBeDefined();
  });

  test('strategy label branches', () => {
    expect(generateSuggestedBom(makeInput({
      selectionPreferences: { preferredVendor: 'InHand' },
    })).summary.selectedVendorStrategy).toBe('preferred_vendor:InHand');
    expect(generateSuggestedBom(makeInput({
      selectionPreferences: { preferSingleVendor: true },
    })).summary.selectedVendorStrategy).toBe('single_vendor_preferred');
    expect(generateSuggestedBom(makeInput({
      selectionPreferences: { preferCheapest: true },
    })).summary.selectedVendorStrategy).toBe('cheapest_acceptable');
  });

  test('needsManagedServices adds recurring managed-service lines', () => {
    const withMs = generateSuggestedBom(makeInput({
      businessContext: { indoorOutdoor: 'indoor', needsGateway: true, needsManagedServices: true },
    }));
    const withoutMs = generateSuggestedBom(makeInput());
    expect(withMs.bomItems.some((i) => i.category === 'managed_service')).toBe(true);
    expect(withoutMs.bomItems.some((i) => i.category === 'managed_service')).toBe(false);
  });
});
