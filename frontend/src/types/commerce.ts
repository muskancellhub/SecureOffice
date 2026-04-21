export type CatalogItemType = 'DEVICE' | 'SERVICE';
export type BillingCycle = 'ONE_TIME' | 'MONTHLY' | 'YEARLY';

export interface CatalogItem {
  id: string;
  type: CatalogItemType;
  name: string;
  sku: string;
  vendor?: string | null;
  vendor_sku?: string | null;
  description: string | null;
  price: number;
  currency: string;
  billing_cycle: BillingCycle;
  availability: string | null;
  attributes: Record<string, any>;
  managed_service_price?: number | null;
  is_active?: boolean;
  created_at: string;
}

export interface CartLine {
  id: string;
  catalog_item_id: string;
  item_name: string;
  item_type: string;
  category?: string | null;
  billing_cycle?: string | null;
  quantity: number;
  unit_price: number;
  currency: string;
  line_total: number;
  applies_to_line_id: string | null;
  applies_to_item_name: string | null;
  created_at: string;
}

export interface Cart {
  id: string;
  status: string;
  lines: CartLine[];
  one_time_subtotal: number;
  monthly_subtotal: number;
  estimated_12_month_total: number;
  currency: string;
}

export interface CatalogSyncResponse {
  synced_count: number;
  created_count: number;
  updated_count: number;
  errors: string[];
  items: CatalogItem[];
}

export interface IntegrationSyncLog {
  integration_name: string;
  scope: string;
  status: 'SUCCESS' | 'PARTIAL' | 'FAILED';
  synced_count: number;
  created_count: number;
  updated_count: number;
  error_excerpt: string | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
}

export interface QuoteLine {
  id: string;
  quote_id: string;
  line_type: 'DEVICE' | 'SERVICE';
  catalog_item_id?: string | null;
  name?: string;
  name_snapshot?: string;
  sku?: string | null;
  sku_snapshot?: string | null;
  vendor?: string | null;
  vendor_snapshot?: string | null;
  qty: number;
  list_price_snapshot?: number;
  final_unit_price_snapshot?: number;
  unit_price: number;
  billing: 'ONE_TIME' | 'RECURRING';
  billing_type?: 'ONE_TIME' | 'RECURRING';
  interval: 'MONTH' | 'YEAR' | null;
  metadata: Record<string, any>;
  parent_line_id: string | null;
  created_at: string;
}

export interface QuoteSummary {
  id: string;
  public_id: string;
  tenant_id: string;
  created_by: string;
  status: string;
  one_time_total: number;
  monthly_total: number;
  projected_12_month_cost: number;
  currency: string;
  default_discount_pct: number;
  incremental_discount_pct: number;
  created_at: string;
  updated_at: string;
}

export interface QuoteDetail extends QuoteSummary {
  lines: QuoteLine[];
}

export interface OrderLine {
  id: string;
  order_id: string;
  line_type: 'DEVICE' | 'SERVICE';
  catalog_item_id?: string | null;
  name: string;
  sku: string | null;
  vendor: string | null;
  qty: number;
  list_price_snapshot?: number;
  final_unit_price_snapshot?: number;
  unit_price: number;
  billing: 'ONE_TIME' | 'RECURRING';
  billing_type?: 'ONE_TIME' | 'RECURRING';
  interval: 'MONTH' | 'YEAR' | null;
  metadata: Record<string, any>;
  parent_line_id: string | null;
  created_at: string;
}

export interface OrderSummary {
  id: string;
  public_id: string;
  tenant_id: string;
  created_by: string;
  quote_id?: string | null;
  quote_public_id?: string | null;
  status: string;
  estimated_delivery_date?: string | null;
  confirmed_delivery_date?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OrderDetail extends OrderSummary {
  lines: OrderLine[];
}

export interface OrderNotificationRecipients {
  tenant_id: string;
  recipients: string[];
  updated_by_user_id: string | null;
  updated_at: string;
}

export interface CustomerPricing {
  tenant_id: string;
  default_discount_pct: number;
  updated_at: string;
}

export interface DealPricing {
  quote_id: string;
  incremental_discount_pct: number;
  updated_at: string;
}

export interface ContractSummary {
  id: string;
  tenant_id: string;
  order_id: string;
  created_by: string;
  status: string;
  term_months: number;
  sla_tier: string;
  entitlements: Record<string, any>;
  start_date: string;
  end_date: string | null;
  created_at: string;
  updated_at: string;
}

export type SubscriptionStatus = 'ACTIVE' | 'PAUSED' | 'CANCELLED';

export interface SubscriptionSummary {
  id: string;
  tenant_id: string;
  contract_id: string;
  order_line_id: string | null;
  name: string;
  sku: string | null;
  vendor: string | null;
  qty: number;
  unit_price: number;
  currency: string;
  interval: 'MONTH' | 'YEAR';
  status: SubscriptionStatus;
  start_date: string;
  end_date: string | null;
  next_billing_date: string | null;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface AssetSummary {
  id: string;
  tenant_id: string;
  contract_id: string | null;
  order_line_id: string | null;
  name: string;
  sku: string | null;
  vendor: string | null;
  asset_type: string;
  status: 'PROVISIONING' | 'ACTIVE' | 'RETIRED';
  owner_user_id: string | null;
  location: string | null;
  serial_number: string | null;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface WorkflowStep {
  id: string;
  workflow_instance_id: string;
  stage_key: string;
  display_name: string;
  sequence: number;
  status: 'PENDING' | 'IN_PROGRESS' | 'DONE' | 'FAILED';
  retries: number;
  started_at: string | null;
  completed_at: string | null;
  metadata: Record<string, any>;
  created_at: string;
}

export interface WorkflowInstance {
  id: string;
  tenant_id: string;
  order_id: string;
  template_key: string;
  status: 'ACTIVE' | 'COMPLETED' | 'FAILED';
  current_stage: string;
  created_at: string;
  updated_at: string;
  steps: WorkflowStep[];
}

export interface BillingMonthPoint {
  month: string;
  one_time_total: number;
  recurring_total: number;
  total: number;
}

export interface BillingOverview {
  past_months: BillingMonthPoint[];
  projected_months: BillingMonthPoint[];
  totals: {
    one_time_last_12_months: number;
    recurring_last_12_months: number;
    projected_next_12_months: number;
    current_monthly_recurring: number;
  };
}

export interface PaymentRecord {
  id: string;
  tenant_id: string;
  invoice_id: string;
  amount: number;
  currency: string;
  status: 'SUCCEEDED' | 'FAILED';
  method: 'MANUAL' | 'CARD' | 'BANK_TRANSFER';
  external_reference: string | null;
  paid_at: string;
  metadata: Record<string, any>;
  created_at: string;
}

export interface InvoiceRecord {
  id: string;
  tenant_id: string;
  subscription_id: string | null;
  billing_month: string;
  amount: number;
  currency: string;
  status: 'DUE' | 'PAID' | 'VOID';
  due_date: string;
  issued_at: string;
  paid_at: string | null;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  payments: PaymentRecord[];
}

export type ValidationStatus = 'PENDING' | 'VERIFIED' | 'FAILED';
export type PaymentMethodType = 'CARD' | 'BANK_TRANSFER' | 'MANUAL';

export interface OnboardingProfile {
  tenant_id: string;
  organization_name: string | null;
  admin_name: string | null;
  admin_email: string | null;
  admin_phone: string | null;
  credit_validation_status: ValidationStatus;
  tax_validation_status: ValidationStatus;
  duns_number: string | null;
  tax_id: string | null;
  company_setup_completed: boolean;
  payment_method_setup: boolean;
  payment_validation_status: ValidationStatus;
  payment_method_type: string | null;
  payment_method_last4: string | null;
  onboarding_completed: boolean;
  metadata: Record<string, any>;
  missing_requirements: string[];
  created_at: string;
  updated_at: string;
}

export interface DesignXSuggestedLine {
  catalog_item_id: string;
  type: CatalogItemType;
  category: string | null;
  name: string;
  sku: string;
  vendor: string | null;
  quantity: number;
  unit_price: number;
  currency: string;
  billing_cycle: BillingCycle;
  reason: string;
  source: string;
  confidence: number;
}

export interface DesignXSuggestBomResponse {
  summary: string;
  suggestions: DesignXSuggestedLine[];
  unavailable_categories: string[];
}

export interface NetworkBomLine {
  line_id: string;
  item_id: string | null;
  sku: string | null;
  source_type: string;
  name: string;
  vendor: string | null;
  category: string | null;
  quantity: number;
  unit_price: number;
  line_total: number;
  selection_reason: string;
  connectivity?: 'wired' | 'wireless' | 'sim';
  cable_type?: 'CAT5' | 'CAT6' | 'CAT6e';
  cable_length_meters?: number;
  price_per_meter?: number;
  wired_drop_count?: number;
  office_area_sqft?: number;
  cost_share_pct?: number;
  is_derived_bom?: boolean;
}

export interface NetworkBomResult {
  line_items: NetworkBomLine[];
  subtotal: number;
  tax: number;
  grand_total: number;
  summary: string;
  assumptions: string[];
}

export interface NetworkTopologyArtifact {
  topology: Record<string, any>;
  drawioXml: string;
  summary: {
    nodeCount: number;
    edgeCount: number;
    assumptions: string[];
  };
}

export type DesignStatus =
  | 'draft'
  | 'reviewed'
  | 'submitted'
  | 'in_review'
  | 'bom_finalized'
  | 'proposal_ready'
  | 'approved'
  | 'order_decomposed'
  | 'fulfillment_in_progress'
  | 'installation_scheduled'
  | 'installed'
  | 'completed';

export type DesignUpdateVisibility = 'internal' | 'customer';
export type InstallMode = 'self_install' | 'remote_assistance' | 'onsite_visit';

export interface DesignStatusHistoryEntry {
  status: DesignStatus;
  changedAt: string;
  changedBy?: string | null;
  note?: string | null;
}

export interface DesignUpdate {
  id: string;
  requestId: string;
  createdAt: string;
  author?: string | null;
  visibility: DesignUpdateVisibility;
  message: string;
}

export interface DesignMilestones {
  estimatedReviewDate?: string | null;
  estimatedProposalDate?: string | null;
  estimatedFulfillmentDate?: string | null;
  estimatedInstallationDate?: string | null;
  confirmedFulfillmentDate?: string | null;
  confirmedInstallationDate?: string | null;
}

export interface DesignInstallAssistance {
  installMode?: InstallMode | null;
  preferredInstallDate?: string | null;
  installNotes?: string | null;
}

export interface DesignDecompositionLine {
  name?: string;
  category?: string | null;
  quantity?: number;
  unitPrice?: number;
  lineTotal?: number;
  vendor?: string | null;
  sourceType?: string | null;
}

export interface DesignDecomposition {
  networkHardware?: DesignDecompositionLine[];
  connectivity?: DesignDecompositionLine[];
  managedServices?: DesignDecompositionLine[];
  installation?: DesignDecompositionLine[];
  accessories?: DesignDecompositionLine[];
}

export interface DesignLead {
  id: string;
  fullName: string;
  email: string;
  companyName: string;
  phone?: string | null;
  notes?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface NetworkDesignSummary {
  id: string;
  quoteId?: string | null;
  orderId?: string | null;
  workflowInstanceId?: string | null;
  designName?: string | null;
  status: DesignStatus;
  statusUpdatedAt?: string | null;
  estimatedCapex: number;
  apCount: number;
  switchCount: number;
  submittedAt?: string | null;
  milestones: DesignMilestones;
  latestUpdate?: string | null;
  nextMilestone?: string | null;
  createdAt: string;
  updatedAt: string;
  lead?: DesignLead | null;
}

// ── Managed Services (per-SKU pricing model) ──────────────────────

export interface ManagedServiceDeviceEntry {
  itemId: string;
  name: string;
  sku: string;
  category: string | null;
  quantity: number;
  managedServicePrice: number;
  excluded: boolean;
}

export interface ManagedServiceCategorySummary {
  group: string;
  groupLabel: string;
  enabled: boolean;
  deviceCount: number;
  excludedCount: number;
  appliedCount: number;
  monthlyTotal: number;
  devices: ManagedServiceDeviceEntry[];
}

export interface ManagedServicesConfig {
  enabledCategories: string[];
  excludedItemIds: string[];
}

export interface ManagedServicesDesignSummary {
  config: ManagedServicesConfig | Record<string, any>;
  categories: ManagedServiceCategorySummary[];
  grandTotalMonthly: number;
}

export interface NetworkDesignDetail extends NetworkDesignSummary {
  calculatorInput: Record<string, any>;
  calculatorResult: Record<string, any>;
  bom: NetworkBomResult | Record<string, any>;
  topology: Record<string, any>;
  drawioXml?: string | null;
  assumptions: string[];
  statusHistory: DesignStatusHistoryEntry[];
  updates: DesignUpdate[];
  installAssistance: DesignInstallAssistance;
  decomposition: DesignDecomposition;
  managedServices?: ManagedServicesDesignSummary;
  metadata: Record<string, any>;
}
