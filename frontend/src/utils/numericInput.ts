/**
 * Sanitize a raw value for the intake form's count fields — every numeric
 * field is a whole, non-negative count (locations, employees, device counts,
 * square footage). You can't have -5 employees, 1.5 cameras, or 0.5 locations.
 *
 * A React controlled `<input type="number">` bypasses the native `min={0}` and
 * `step="1"` constraints because the value is driven by component state, not
 * the DOM — so the browser never blocks negatives (BUG-001/004/005), decimals
 * (BUG-003), or scientific notation like "1e99" (BUG-022). All must be rejected
 * in the onChange handler instead.
 *
 * A plain-digits test (`/^\d+$/`) is the simplest correct rule: it accepts only
 * a run of digits, which rules out signs, decimal points, exponents, and other
 * non-numeric text in one check. An upper bound then rejects absurd magnitudes
 * (e.g. "99999999999999") that would still be plain digits.
 *
 * Returns the value to store, or `null` to reject the change (keep the previous
 * value). '' (a cleared field) is allowed through.
 */

// Generous ceiling: above the largest plausible square footage / device count,
// but far below the astronomical values that blow up the calculator.
export const MAX_COUNT = 10_000_000;

export function sanitizeCountInput(raw: string): string | null {
  if (raw === '') return '';
  if (!/^\d+$/.test(raw)) return null; // digits only — rejects '-1', '1.5', '1e99', 'abc'
  if (Number(raw) > MAX_COUNT) return null; // reject absurd magnitudes
  return raw;
}
