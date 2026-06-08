// Component catalog + pricing types (Secure Office Phase 4 admin portal).

export type FinancialModel = 'CAPEX' | 'OPEX' | 'BOTH';
export type Billing = 'ONE_TIME' | 'RECURRING';
export type Interval = 'MONTH' | 'YEAR';
export type Uom = 'PER_DEVICE' | 'PER_LINE' | 'PER_SEAT' | 'PER_HOUR' | 'ONE_TIME' | 'PER_DID';

export const COMPONENT_TYPES = [
  'DEVICE', 'CLOUD_CONTROLLER', 'LINE_CHARGE', 'MANAGED_SERVICE', 'SIM', 'BACKUP_SIM',
  'INSTALLATION', 'PROFESSIONAL_SERVICES', 'MAINTENANCE', 'LICENSE', 'ACCESSORY',
] as const;
export type ComponentType = (typeof COMPONENT_TYPES)[number];

export interface ProductComponent {
  id: string;
  product_id: string;
  component_type: ComponentType;
  financial_model: FinancialModel;
  label: string;
  vendor_component_sku: string | null;
  vendor_cost: number;
  msrp: number | null;
  uom: Uom;
  billing: Billing;
  interval: Interval | null;
  margin_pct: number | null;
  leasing_pct: number | null;
  default_qty: number;
  is_required: boolean;
  is_active: boolean;
  attributes: Record<string, any>;
}

export interface Product {
  id: string;
  vendor: string;
  technology: string;
  sku: string;
  vendor_sku: string | null;
  name: string;
  description: string | null;
  default_financial_model: FinancialModel;
  margin_pct: number | null;
  leasing_pct: number | null;
  is_active: boolean;
  attributes: Record<string, any>;
  components: ProductComponent[];
}

export interface FinancingTerms {
  id: string;
  name: string;
  term_months: number;
  annual_rate_pct: number;
  subscription_interval: Interval;
  is_default: boolean;
  is_active: boolean;
}

export interface PreviewLine {
  component_id: string;
  component_type: string;
  label: string;
  vendor_component_sku: string | null;
  qty: number;
  margin_pct: number;
  margin_source: string;
  billing: Billing;
  interval: Interval | null;
  financed: boolean;
  unit_price: number;
  line_total: number;
  one_time_total: number;
  monthly_total: number;
  parent_component_id: string | null;
}

export interface PreviewResult {
  product: { id: string; sku: string; name: string; vendor: string };
  financial_model: FinancialModel;
  interval: Interval;
  term_months: number;
  annual_rate_pct: number;
  lines: PreviewLine[];
  one_time_total: number;
  monthly_total: number;
  recurring_total_at_interval: number;
  projected_term_cost: number;
}
