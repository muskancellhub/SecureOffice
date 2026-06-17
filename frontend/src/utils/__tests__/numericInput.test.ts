import { describe, expect, it } from 'vitest';

import { sanitizeCountInput, MAX_COUNT } from '../numericInput';

describe('sanitizeCountInput — intake count fields', () => {
  it('rejects negative numbers (BUG-001/004/005)', () => {
    expect(sanitizeCountInput('-1')).toBeNull();
    expect(sanitizeCountInput('-5')).toBeNull();
    expect(sanitizeCountInput('-10')).toBeNull();
    expect(sanitizeCountInput('-500')).toBeNull();
  });

  it('rejects scientific notation and absurd magnitudes (BUG-022)', () => {
    expect(sanitizeCountInput('1e99')).toBeNull();
    expect(sanitizeCountInput('1e3')).toBeNull(); // 'e' is not a digit
    expect(sanitizeCountInput(String(MAX_COUNT + 1))).toBeNull();
    expect(sanitizeCountInput(String(MAX_COUNT))).toBe(String(MAX_COUNT));
  });

  it('rejects decimals — counts must be whole numbers (BUG-003)', () => {
    expect(sanitizeCountInput('1.5')).toBeNull();
    expect(sanitizeCountInput('0.5')).toBeNull();
    expect(sanitizeCountInput('2.7')).toBeNull();
    expect(sanitizeCountInput('-1.5')).toBeNull();
  });

  it('rejects a lone minus and other non-numeric input', () => {
    expect(sanitizeCountInput('-')).toBeNull();
    expect(sanitizeCountInput('abc')).toBeNull();
  });

  it('accepts zero and positive whole numbers, preserving the raw string', () => {
    expect(sanitizeCountInput('0')).toBe('0');
    expect(sanitizeCountInput('1')).toBe('1');
    expect(sanitizeCountInput('15')).toBe('15');
    expect(sanitizeCountInput('5000')).toBe('5000');
  });

  it('allows clearing the field (empty string)', () => {
    expect(sanitizeCountInput('')).toBe('');
  });
});
