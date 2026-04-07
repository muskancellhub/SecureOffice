import type {
  BomItem,
  BomTotals,
  CalculatorResult,
  DrawioOutput,
  PreviewPayload,
  SelectedProducts,
} from './types';

type BuildPreviewPayloadInput = {
  calculatorResult: CalculatorResult;
  selectedProducts: SelectedProducts;
  bomItems: BomItem[];
  totals: BomTotals;
  topology: PreviewPayload['topology'];
  drawio: DrawioOutput;
  selectedVendorStrategy: string;
  notes: string[];
};

const resolveRecommendedIndoorAps = (calculatorResult: CalculatorResult): number => {
  const byCounts = Number(calculatorResult.counts?.indoorAPsFinal || 0);
  if (byCounts > 0) return Math.floor(byCounts);

  const bySummary = Number(calculatorResult.summary?.recommendedIndoorAPs || 0);
  if (bySummary > 0) return Math.floor(bySummary);

  return 0;
};

export const buildPreviewPayload = (input: BuildPreviewPayloadInput): PreviewPayload => {
  return {
    summary: {
      recommendedIndoorAPs: resolveRecommendedIndoorAps(input.calculatorResult),
      selectedVendorStrategy: input.selectedVendorStrategy,
      estimatedHardwareSubtotal: input.totals.hardwareSubtotal,
      estimatedServicesSubtotal: input.totals.servicesSubtotal,
      estimatedGrandTotal: input.totals.grandTotal,
    },
    selectedProducts: {
      ap: input.selectedProducts.ap,
      switch: input.selectedProducts.switch,
      gateway: input.selectedProducts.gateway,
      cellularBackup: input.selectedProducts.cellularBackup,
    },
    bomItems: input.bomItems,
    topology: input.topology,
    drawio: input.drawio,
    notes: input.notes,
  };
};

