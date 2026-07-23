import { describe, expect, test } from 'vitest';

import { generateConfigurationPreviewAndOrderPayload } from '../pipeline';
import type { PipelineInput } from '../types';
import { calculatorFixture, catalogFixture, partialCalculatorResult } from './fixtures';

const makeInput = (overrides: Partial<PipelineInput> = {}): PipelineInput => ({
  calculatorResult: calculatorFixture,
  businessContext: { indoorOutdoor: 'indoor', needsGateway: true, needsCellularBackup: true },
  catalog: catalogFixture,
  ...overrides,
});

describe('pipeline output shape', () => {
  test('happy path produces candidates, BOM, drawio, and both payloads', () => {
    const out = generateConfigurationPreviewAndOrderPayload(makeInput());
    expect(out.retrievedCandidates.aps.length).toBeGreaterThan(0);
    expect(out.selectedProducts.ap).toBeDefined();
    expect(out.bomItems.length).toBeGreaterThan(0);
    expect(out.drawio.xml).toContain('mxGraphModel');
    expect(out.previewPayload).toBeDefined();
    expect(out.mailboxPayload).toBeDefined();
  });
});

describe('vendor strategy labels', () => {
  const labelFor = (selectionPreferences: PipelineInput['selectionPreferences']) =>
    generateConfigurationPreviewAndOrderPayload(makeInput({ selectionPreferences }))
      .previewPayload.summary.selectedVendorStrategy;

  test('explicit vendor', () => {
    expect(labelFor({ preferredVendor: 'Meraki' })).toBe('preferred_vendor:Meraki');
  });

  test('auto falls through to balanced', () => {
    expect(labelFor({ preferredVendor: 'auto' })).toBe('balanced_auto');
  });

  test('single vendor preferred', () => {
    expect(labelFor({ preferSingleVendor: true })).toBe('single_vendor_preferred');
  });

  test('cheapest acceptable', () => {
    expect(labelFor({ preferCheapest: true })).toBe('cheapest_acceptable');
  });

  test('no preferences -> balanced', () => {
    expect(labelFor(undefined)).toBe('balanced_auto');
  });
});

describe('single-vendor majority note', () => {
  test('preferSingleVendor appends a majority note', () => {
    const out = generateConfigurationPreviewAndOrderPayload(makeInput({
      selectionPreferences: { preferSingleVendor: true, preferredVendor: 'auto' },
    }));
    const note = out.previewPayload.notes.find((n) => n.includes('Single-vendor preference favored'));
    expect(note).toBeDefined();
  });

  test('no preference -> no majority note', () => {
    const out = generateConfigurationPreviewAndOrderPayload(makeInput());
    const note = out.previewPayload.notes.find((n) => n.includes('Single-vendor preference favored'));
    expect(note).toBeUndefined();
  });
});

describe('include overrides beat businessContext', () => {
  test('includeGateway/includeCellularBackup=false suppress selection', () => {
    const out = generateConfigurationPreviewAndOrderPayload(makeInput({
      includeGateway: false,
      includeCellularBackup: false,
    }));
    expect(out.selectedProducts.gateway).toBeUndefined();
    expect(out.selectedProducts.cellularBackup).toBeUndefined();
  });

  test('includeCellularBackup=true forces cellular even when context says no', () => {
    const out = generateConfigurationPreviewAndOrderPayload(makeInput({
      businessContext: { indoorOutdoor: 'indoor', needsGateway: false, needsCellularBackup: false },
      includeCellularBackup: true,
    }));
    expect(out.selectedProducts.cellularBackup).toBeDefined();
  });
});

describe('warning accumulation', () => {
  test('empty catalog accumulates validation + engine warnings into mailbox payload', () => {
    const out = generateConfigurationPreviewAndOrderPayload(makeInput({ catalog: [] }));
    expect(out.warnings.some((w) => w.includes('Catalog is empty'))).toBe(true);
    expect(out.warnings.some((w) => w.toLowerCase().includes('no'))).toBe(true);
    // every pipeline warning is carried into the mailbox payload's fulfillment notes
    const warningNotes = out.mailboxPayload.fulfillmentNotes.filter((n) => n.startsWith('Warning:'));
    expect(warningNotes.length).toBe(out.warnings.length);
  });

  test('negative counts produce both negative-count warnings', () => {
    const out = generateConfigurationPreviewAndOrderPayload(makeInput({
      calculatorResult: partialCalculatorResult({
        counts: { indoorAPsFinal: -2, switchCount: -1 },
      }),
    }));
    expect(out.warnings.some((w) => w.includes('AP count is negative'))).toBe(true);
    expect(out.warnings.some((w) => w.includes('switch count is negative'))).toBe(true);
  });

  test('invalid catalog price surfaces in warnings', () => {
    const badItem = { ...catalogFixture[0], model: 'BADPRICE', price: Number.NaN };
    const out = generateConfigurationPreviewAndOrderPayload(makeInput({
      catalog: [...catalogFixture, badItem],
    }));
    expect(out.warnings.some((w) => w.includes('BADPRICE') && w.includes('invalid price'))).toBe(true);
  });
});
