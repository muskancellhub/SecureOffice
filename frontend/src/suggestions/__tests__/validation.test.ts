import { describe, expect, test } from 'vitest';

import { validatePipelineInput } from '../validation';
import type { CalculatorResult, PipelineInput } from '../types';
import { calculatorFixture, catalogFixture, partialCalculatorResult } from './fixtures';

const makeInput = (overrides: Partial<PipelineInput> = {}): PipelineInput => ({
  calculatorResult: calculatorFixture,
  businessContext: { indoorOutdoor: 'indoor' },
  catalog: catalogFixture,
  ...overrides,
});

const calc = (
  counts: Partial<CalculatorResult['counts']>,
  summary: Partial<CalculatorResult['summary']> = {},
) => partialCalculatorResult({ counts, summary });

describe('validatePipelineInput', () => {
  test('fully valid input -> no warnings', () => {
    expect(validatePipelineInput(makeInput())).toEqual([]);
  });

  test('empty catalog warns', () => {
    const warnings = validatePipelineInput(makeInput({ catalog: [] }));
    expect(warnings.some((w) => w.includes('Catalog is empty'))).toBe(true);
  });

  test('AP count missing from both sources warns', () => {
    const warnings = validatePipelineInput(makeInput({
      calculatorResult: calc({ switchCount: 1 }),
    }));
    expect(warnings.some((w) => w.includes('Missing calculator AP count'))).toBe(true);
  });

  test('AP count present via summary alone is accepted', () => {
    const warnings = validatePipelineInput(makeInput({
      calculatorResult: calc({ switchCount: 1 }, { recommendedIndoorAPs: 3 }),
    }));
    expect(warnings.some((w) => w.includes('Missing calculator AP count'))).toBe(false);
  });

  test('switch count missing from both sources warns', () => {
    const warnings = validatePipelineInput(makeInput({
      calculatorResult: calc({ indoorAPsFinal: 4 }),
    }));
    expect(warnings.some((w) => w.includes('Missing calculator switch count'))).toBe(true);
  });

  test('negative AP and switch counts warn individually', () => {
    const warnings = validatePipelineInput(makeInput({
      calculatorResult: calc({ indoorAPsFinal: -1, switchCount: -1 }),
    }));
    expect(warnings.some((w) => w.includes('AP count is negative'))).toBe(true);
    expect(warnings.some((w) => w.includes('switch count is negative'))).toBe(true);
  });

  test('non-finite or negative catalog price warns; null/undefined price passes', () => {
    const bad = { ...catalogFixture[0], model: 'NEG', price: -5 };
    const nan = { ...catalogFixture[1], model: 'NAN', price: Number.NaN };
    const nullPrice = { ...catalogFixture[2], model: 'NULLP', price: undefined };
    const warnings = validatePipelineInput(makeInput({
      catalog: [bad, nan, nullPrice],
    }));
    expect(warnings.filter((w) => w.includes('invalid price'))).toHaveLength(2);
    expect(warnings.some((w) => w.includes('NULLP'))).toBe(false);
  });
});
