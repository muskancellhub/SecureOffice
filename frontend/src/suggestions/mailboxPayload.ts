import type {
  BomItem,
  BomTotals,
  CalculatorResult,
  CustomerContext,
  MailboxOrderPayload,
  SelectedProducts,
  TopologyDiagram,
} from './types';

type BuildMailboxPayloadInput = {
  customer?: CustomerContext;
  calculatorResult: CalculatorResult;
  selectedProducts: SelectedProducts;
  bomItems: BomItem[];
  totals: BomTotals;
  topology: TopologyDiagram;
  drawioXml: string;
  warnings?: string[];
};

const BASE_FULFILLMENT_NOTES = [
  'Customer-entered environment details may require verification during review.',
  'Pricing in this payload is estimate-level and may be non-binding.',
  'Design is generated from calculator and catalog data, not a certified site survey.',
  'Installation assumptions are included in BOM placeholders and should be validated before execution.',
];

export const buildMailboxOrderPayload = (input: BuildMailboxPayloadInput): MailboxOrderPayload => {
  const warningNotes = (input.warnings || []).map((warning) => `Warning: ${warning}`);

  return {
    customer: input.customer || {},
    calculatorResult: input.calculatorResult,
    selectedProducts: {
      ap: input.selectedProducts.ap,
      switch: input.selectedProducts.switch,
      gateway: input.selectedProducts.gateway,
      cellularBackup: input.selectedProducts.cellularBackup,
    },
    bomItems: input.bomItems,
    totals: input.totals,
    topology: input.topology,
    drawioXml: input.drawioXml,
    fulfillmentNotes: [...BASE_FULFILLMENT_NOTES, ...warningNotes],
  };
};

