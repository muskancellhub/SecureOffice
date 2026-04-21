import { api } from './client';
import type {
  AssetSummary,
  BillingOverview,
  Cart,
  CatalogItem,
  CatalogSyncResponse,
  ContractSummary,
  CustomerPricing,
  DealPricing,
  ManagedServicesDesignSummary,
  DesignInstallAssistance,
  DesignMilestones,
  DesignStatus,
  DesignUpdateVisibility,
  DesignXSuggestBomResponse,
  NetworkBomResult,
  NetworkDesignDetail,
  NetworkDesignSummary,
  NetworkTopologyArtifact,
  OnboardingProfile,
  InvoiceRecord,
  IntegrationSyncLog,
  OrderNotificationRecipients,
  OrderDetail,
  OrderSummary,
  PaymentRecord,
  QuoteDetail,
  QuoteSummary,
  SubscriptionStatus,
  SubscriptionSummary,
  WorkflowInstance,
} from '../types/commerce';

const authHeaders = (accessToken: string) => ({ Authorization: `Bearer ${accessToken}` });

export const syncCdwRouters = async (accessToken: string, query?: string, limit = 20) => {
  const { data } = await api.post(
    '/integrations/cdw/sync-routers',
    {
      query: query || 'business routers with sku, brand, model, ports, wifi standard, price and availability',
      limit,
    },
    { headers: authHeaders(accessToken) },
  );
  return data as CatalogSyncResponse;
};

export const getCdwLastSync = async (accessToken: string) => {
  const { data } = await api.get('/integrations/cdw/last-sync', { headers: authHeaders(accessToken) });
  return data as IntegrationSyncLog | null;
};

export const syncPapiDevices = async (
  accessToken: string,
  options?: { page_size?: number; max_pages?: number; eip?: boolean; classic?: boolean },
) => {
  const { data } = await api.post(
    '/integrations/papi/sync-devices',
    {
      page_size: options?.page_size ?? 100,
      max_pages: options?.max_pages ?? 20,
      eip: options?.eip ?? true,
      classic: options?.classic ?? true,
    },
    { headers: authHeaders(accessToken) },
  );
  return data as CatalogSyncResponse;
};

export const getPapiLastSync = async (accessToken: string) => {
  const { data } = await api.get('/integrations/papi/last-sync', { headers: authHeaders(accessToken) });
  return data as IntegrationSyncLog | null;
};

export const getCatalog = async (
  accessToken: string,
  params: {
    type?: 'DEVICE' | 'SERVICE';
    category?: string;
    service_kind?: string;
    search?: string;
    brand?: string;
    wifi_standard?: string;
    availability?: string;
    min_price?: number;
    max_price?: number;
    min_ports?: number;
    sort?: 'recommended' | 'price_low' | 'price_high' | 'availability';
    page?: number;
    page_size?: number;
  },
) => {
  const { data } = await api.get('/catalog', { headers: authHeaders(accessToken), params });
  return data as CatalogItem[];
};

export const getCatalogItem = async (accessToken: string, itemId: string) => {
  const { data } = await api.get(`/catalog/${itemId}`, { headers: authHeaders(accessToken) });
  return data as CatalogItem;
};

export const updateManagedService = async (
  accessToken: string,
  itemId: string,
  payload: { price?: number; is_active?: boolean; features?: string[] },
) => {
  const { data } = await api.patch(`/catalog/services/${itemId}`, payload, { headers: authHeaders(accessToken) });
  return data as CatalogItem;
};

export const getCart = async (accessToken: string) => {
  const { data } = await api.get('/cart', { headers: authHeaders(accessToken) });
  return data as Cart;
};

export const addCartLine = async (
  accessToken: string,
  payload: { catalog_item_id: string; quantity?: number; applies_to_line_id?: string },
) => {
  const { data } = await api.post('/cart/lines', payload, { headers: authHeaders(accessToken) });
  return data as Cart;
};

export const updateCartLine = async (
  accessToken: string,
  lineId: string,
  payload: { quantity?: number; catalog_item_id?: string },
) => {
  const { data } = await api.patch(`/cart/lines/${lineId}`, payload, { headers: authHeaders(accessToken) });
  return data as Cart;
};

export const removeCartLine = async (accessToken: string, lineId: string) => {
  const { data } = await api.delete(`/cart/lines/${lineId}`, { headers: authHeaders(accessToken) });
  return data as Cart;
};

export const generateQuote = async (accessToken: string) => {
  const { data } = await api.post('/quotes', {}, { headers: authHeaders(accessToken) });
  if (data?.quote_id) {
    return getQuote(accessToken, data.quote_id as string);
  }
  return data as QuoteDetail;
};

export const listQuotes = async (accessToken: string) => {
  const { data } = await api.get('/quotes', { headers: authHeaders(accessToken) });
  return data as QuoteSummary[];
};

export const getQuote = async (accessToken: string, quoteId: string) => {
  const { data } = await api.get(`/quotes/${quoteId}`, { headers: authHeaders(accessToken) });
  return data as QuoteDetail;
};

export const sendQuote = async (accessToken: string, quoteId: string) => {
  const { data } = await api.post(`/quotes/${quoteId}/send`, {}, { headers: authHeaders(accessToken) });
  return data as QuoteDetail;
};

export const acceptQuote = async (accessToken: string, quoteId: string) => {
  const { data } = await api.post(`/quotes/${quoteId}/accept`, {}, { headers: authHeaders(accessToken) });
  return data as QuoteDetail;
};

export const convertQuote = async (accessToken: string, quoteId: string) => {
  const { data } = await api.post(`/quotes/${quoteId}/convert`, {}, { headers: authHeaders(accessToken) });
  return data as OrderDetail;
};

export const listOrders = async (accessToken: string) => {
  const { data } = await api.get('/orders', { headers: authHeaders(accessToken) });
  return data as OrderSummary[];
};

export const getOrder = async (accessToken: string, orderId: string) => {
  const { data } = await api.get(`/orders/${orderId}`, { headers: authHeaders(accessToken) });
  return data as OrderDetail;
};

export const getOrderNotificationRecipients = async (accessToken: string) => {
  const { data } = await api.get('/orders/notifications/recipients', { headers: authHeaders(accessToken) });
  return data as OrderNotificationRecipients;
};

export const updateOrderNotificationRecipients = async (accessToken: string, recipients: string[]) => {
  const { data } = await api.put(
    '/orders/notifications/recipients',
    { recipients },
    { headers: authHeaders(accessToken) },
  );
  return data as OrderNotificationRecipients;
};

export const getBillingOverview = async (accessToken: string, params?: { months_back?: number; months_forward?: number }) => {
  const { data } = await api.get('/billing/overview', { headers: authHeaders(accessToken), params });
  return data as BillingOverview;
};

export const listInvoices = async (accessToken: string) => {
  const { data } = await api.get('/billing/invoices', { headers: authHeaders(accessToken) });
  return data as InvoiceRecord[];
};

export const runInvoicing = async (accessToken: string, billingMonth?: string) => {
  const { data } = await api.post('/billing/invoices/run', { billing_month: billingMonth || null }, { headers: authHeaders(accessToken) });
  return data as InvoiceRecord[];
};

export const recordInvoicePayment = async (
  accessToken: string,
  invoiceId: string,
  payload?: { amount?: number; method?: 'MANUAL' | 'CARD' | 'BANK_TRANSFER'; external_reference?: string },
) => {
  const { data } = await api.post(`/billing/invoices/${invoiceId}/payments`, payload || {}, { headers: authHeaders(accessToken) });
  return data as PaymentRecord;
};

export const listContracts = async (accessToken: string) => {
  const { data } = await api.get('/lifecycle/contracts', { headers: authHeaders(accessToken) });
  return data as ContractSummary[];
};

export const listSubscriptions = async (accessToken: string, status?: SubscriptionStatus) => {
  const { data } = await api.get('/lifecycle/subscriptions', {
    headers: authHeaders(accessToken),
    params: status ? { status } : undefined,
  });
  return data as SubscriptionSummary[];
};

export const updateSubscriptionStatus = async (accessToken: string, subscriptionId: string, status: SubscriptionStatus) => {
  const { data } = await api.patch(`/lifecycle/subscriptions/${subscriptionId}/status`, { status }, { headers: authHeaders(accessToken) });
  return data as SubscriptionSummary;
};

export const listAssets = async (accessToken: string) => {
  const { data } = await api.get('/lifecycle/assets', { headers: authHeaders(accessToken) });
  return data as AssetSummary[];
};

export const getOrderWorkflow = async (accessToken: string, orderId: string) => {
  const { data } = await api.get(`/lifecycle/orders/${orderId}/workflow`, { headers: authHeaders(accessToken) });
  return data as WorkflowInstance;
};

export const advanceOrderWorkflow = async (accessToken: string, orderId: string) => {
  const { data } = await api.post(`/lifecycle/orders/${orderId}/workflow/advance`, {}, { headers: authHeaders(accessToken) });
  return data as WorkflowInstance;
};

export const getCustomerPricing = async (accessToken: string) => {
  const { data } = await api.get('/pricing/customer', { headers: authHeaders(accessToken) });
  return data as CustomerPricing;
};

export const updateCustomerPricing = async (accessToken: string, payload: { default_discount_pct: number }) => {
  const { data } = await api.put('/pricing/customer', payload, { headers: authHeaders(accessToken) });
  return data as CustomerPricing;
};

export const updateDealPricing = async (accessToken: string, quoteId: string, payload: { incremental_discount_pct: number }) => {
  const { data } = await api.put(`/pricing/deal/${quoteId}`, payload, { headers: authHeaders(accessToken) });
  return data as DealPricing;
};

export const getOnboardingProfile = async (accessToken: string) => {
  const { data } = await api.get('/onboarding/profile', { headers: authHeaders(accessToken) });
  return data as OnboardingProfile;
};

export const updateOnboardingProfile = async (
  accessToken: string,
  payload: {
    organization_name?: string;
    admin_name?: string;
    admin_email?: string;
    admin_phone?: string;
    credit_validation_status?: 'PENDING' | 'VERIFIED' | 'FAILED';
    tax_validation_status?: 'PENDING' | 'VERIFIED' | 'FAILED';
    duns_number?: string;
    tax_id?: string;
    company_setup_completed?: boolean;
    payment_method_setup?: boolean;
    metadata?: Record<string, any>;
  },
) => {
  const { data } = await api.put('/onboarding/profile', payload, { headers: authHeaders(accessToken) });
  return data as OnboardingProfile;
};

export const validatePaymentMethod = async (
  accessToken: string,
  payload: { payment_method_type: 'CARD' | 'BANK_TRANSFER' | 'MANUAL'; last4?: string; external_reference?: string },
) => {
  const { data } = await api.post('/onboarding/payment/validate', payload, { headers: authHeaders(accessToken) });
  return data as OnboardingProfile;
};

export const suggestDesignXBom = async (
  accessToken: string,
  payload: {
    requirement: string;
    employee_count: number;
    site_count: number;
    existing_customer?: boolean;
  },
) => {
  const { data } = await api.post('/integrations/designx/suggest-bom', payload, { headers: authHeaders(accessToken) });
  return data as DesignXSuggestBomResponse;
};

export const generateNetworkBom = async (
  accessToken: string,
  payload: {
    calculatorResult: Record<string, any>;
    businessContext?: Record<string, any>;
    preferences?: Record<string, any>;
  },
) => {
  const { data } = await api.post('/integrations/network/generate-bom', payload, { headers: authHeaders(accessToken) });
  return data as NetworkBomResult;
};

export const generateNetworkTopology = async (
  accessToken: string,
  payload: {
    bom: Record<string, any>;
    designId?: string;
    businessContext?: Record<string, any>;
  },
) => {
  const { data } = await api.post('/integrations/network/generate-topology', payload, { headers: authHeaders(accessToken) });
  return data as NetworkTopologyArtifact;
};

export const saveNetworkDesign = async (
  accessToken: string,
  payload: {
    designId?: string;
    designName?: string;
    calculatorInput?: Record<string, any>;
    calculatorResult?: Record<string, any>;
    bom?: Record<string, any>;
    topology?: Record<string, any>;
    drawioXml?: string;
    assumptions?: string[];
    submit?: boolean;
    status?: DesignStatus;
    milestones?: DesignMilestones;
    installAssistance?: DesignInstallAssistance;
    lead?: {
      fullName?: string;
      email?: string;
      companyName?: string;
      phone?: string;
      notes?: string;
    };
  },
) => {
  const { data } = await api.post('/designs', payload, { headers: authHeaders(accessToken) });
  return data as NetworkDesignDetail;
};

export const submitNetworkDesign = async (
  accessToken: string,
  designId: string,
  payload: {
    lead: {
      fullName: string;
      email: string;
      companyName: string;
      phone?: string;
      notes?: string;
    };
  },
) => {
  const { data } = await api.post(`/designs/${designId}/submit`, payload, { headers: authHeaders(accessToken) });
  return data as NetworkDesignDetail;
};

export const listNetworkDesigns = async (
  accessToken: string,
  params?: {
    submitted_only?: boolean;
  },
) => {
  const { data } = await api.get('/designs', { headers: authHeaders(accessToken), params });
  return data as NetworkDesignSummary[];
};

export const listOpsNetworkSubmissions = async (accessToken: string) => {
  const { data } = await api.get('/designs/ops/submissions', { headers: authHeaders(accessToken) });
  return data as NetworkDesignSummary[];
};

export const getNetworkDesign = async (accessToken: string, designId: string) => {
  const { data } = await api.get(`/designs/${designId}`, { headers: authHeaders(accessToken) });
  return data as NetworkDesignDetail;
};

export const updateNetworkDesignStatus = async (
  accessToken: string,
  designId: string,
  status: DesignStatus,
  options?: {
    note?: string;
    noteVisibility?: DesignUpdateVisibility;
  },
) => {
  const { data } = await api.patch(
    `/designs/${designId}/status`,
    { status, note: options?.note, noteVisibility: options?.noteVisibility },
    { headers: authHeaders(accessToken) },
  );
  return data as NetworkDesignDetail;
};

export const updateNetworkDesignMilestones = async (
  accessToken: string,
  designId: string,
  milestones: DesignMilestones,
) => {
  const { data } = await api.patch(
    `/designs/${designId}/milestones`,
    { milestones },
    { headers: authHeaders(accessToken) },
  );
  return data as NetworkDesignDetail;
};

export const updateNetworkDesignInstallAssistance = async (
  accessToken: string,
  designId: string,
  installAssistance: DesignInstallAssistance,
) => {
  const { data } = await api.patch(
    `/designs/${designId}/install-assistance`,
    { installAssistance },
    { headers: authHeaders(accessToken) },
  );
  return data as NetworkDesignDetail;
};

export const addNetworkDesignUpdate = async (
  accessToken: string,
  designId: string,
  payload: {
    visibility: DesignUpdateVisibility;
    message: string;
  },
) => {
  const { data } = await api.post(
    `/designs/${designId}/updates`,
    { update: payload },
    { headers: authHeaders(accessToken) },
  );
  return data as NetworkDesignDetail;
};

// ---------------------------------------------------------------------------
// Zabbix monitoring
// ---------------------------------------------------------------------------

export const fetchZabbixDashboard = async (accessToken: string) => {
  const { data } = await api.get('/zabbix/dashboard', { headers: authHeaders(accessToken) });
  return data;
};

export const fetchZabbixHosts = async (accessToken: string) => {
  const { data } = await api.get('/zabbix/hosts', { headers: authHeaders(accessToken) });
  return data;
};

export const fetchZabbixProblems = async (accessToken: string, limit = 100) => {
  const { data } = await api.get('/zabbix/problems', { headers: authHeaders(accessToken), params: { limit } });
  return data;
};

export const fetchZabbixTriggers = async (accessToken: string, limit = 100) => {
  const { data } = await api.get('/zabbix/triggers', { headers: authHeaders(accessToken), params: { limit } });
  return data;
};

export const fetchZabbixHostMetrics = async (accessToken: string, hostId: string) => {
  const { data } = await api.get(`/zabbix/hosts/${hostId}/metrics`, { headers: authHeaders(accessToken) });
  return data;
};

// ---------------------------------------------------------------------------
// Managed Services (per-SKU pricing)
// ---------------------------------------------------------------------------

export const getDesignManagedServices = async (accessToken: string, designId: string) => {
  const { data } = await api.get(`/designs/${designId}/managed-services`, { headers: authHeaders(accessToken) });
  return data as ManagedServicesDesignSummary;
};

export const updateDesignManagedServices = async (
  accessToken: string,
  designId: string,
  config: { enabledCategories: string[]; excludedItemIds: string[] },
) => {
  const { data } = await api.put(`/designs/${designId}/managed-services`, config, {
    headers: authHeaders(accessToken),
  });
  return data as ManagedServicesDesignSummary;
};

export const updateDeviceManagedServicePrice = async (
  accessToken: string,
  itemId: string,
  managedServicePrice: number | null,
) => {
  const { data } = await api.patch(
    `/catalog/devices/${itemId}/managed-service-price`,
    { managed_service_price: managedServicePrice },
    { headers: authHeaders(accessToken) },
  );
  return data as CatalogItem;
};

export const bulkUpdateManagedServicePrices = async (
  accessToken: string,
  updates: { item_id: string; managed_service_price: number | null }[],
) => {
  const { data } = await api.put('/catalog/devices/managed-service-prices', { updates }, {
    headers: authHeaders(accessToken),
  });
  return data as { updated_count: number };
};
