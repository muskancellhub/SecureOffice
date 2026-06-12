// Admin catalog + pricing API (Secure Office Phase 4).
import { api } from './client';
import type {
  FinancingTerms,
  PreviewResult,
  Product,
  ProductComponent,
} from '../types/products';

const authHeaders = (accessToken: string) => ({ Authorization: `Bearer ${accessToken}` });

// ── products ────────────────────────────────────────────────────────────────
export const listProducts = async (
  accessToken: string,
  params: { vendor?: string; technology?: string; financial_model?: string; is_active?: boolean } = {},
) => {
  const { data } = await api.get('/products', { headers: authHeaders(accessToken), params });
  return data as Product[];
};

export const getProduct = async (accessToken: string, productId: string) => {
  const { data } = await api.get(`/products/${productId}`, { headers: authHeaders(accessToken) });
  return data as Product;
};

export const createProduct = async (accessToken: string, payload: Partial<Product>) => {
  const { data } = await api.post('/products', payload, { headers: authHeaders(accessToken) });
  return data as Product;
};

export const updateProduct = async (accessToken: string, productId: string, payload: Partial<Product>) => {
  const { data } = await api.patch(`/products/${productId}`, payload, { headers: authHeaders(accessToken) });
  return data as Product;
};

export const addComponent = async (accessToken: string, productId: string, payload: Partial<ProductComponent>) => {
  const { data } = await api.post(`/products/${productId}/components`, payload, { headers: authHeaders(accessToken) });
  return data as ProductComponent;
};

export const updateComponent = async (accessToken: string, componentId: string, payload: Partial<ProductComponent>) => {
  const { data } = await api.patch(`/products/components/${componentId}`, payload, { headers: authHeaders(accessToken) });
  return data as ProductComponent;
};

// ── live price preview ────────────────────────────────────────────────────────
export const componentPreview = async (
  accessToken: string,
  payload: { product_id: string; financial_model: string; interval: string; selections: Record<string, number> },
) => {
  const { data } = await api.post('/pricing/component-preview', payload, { headers: authHeaders(accessToken) });
  return data as PreviewResult;
};

// ── financing terms ───────────────────────────────────────────────────────────
export const listFinancingTerms = async (accessToken: string) => {
  const { data } = await api.get('/pricing/financing-terms', { headers: authHeaders(accessToken) });
  return data as FinancingTerms[];
};

export const createFinancingTerms = async (accessToken: string, payload: Partial<FinancingTerms>) => {
  const { data } = await api.post('/pricing/financing-terms', payload, { headers: authHeaders(accessToken) });
  return data as FinancingTerms;
};

// ── customer commercial config ────────────────────────────────────────────────
export interface CommercialConfig {
  tenant_id: string;
  default_discount_pct: number;
  default_margin_pct: number;
  opex_eligible: boolean;
  credit_status: string;
  credit_limit: number | null;
}

export const updateCustomerCommercial = async (
  accessToken: string,
  tenantId: string,
  payload: { default_margin_pct?: number | null; opex_eligible?: boolean; credit_status?: string; credit_limit?: number },
) => {
  const { data } = await api.patch(`/pricing/customers/${tenantId}/commercial`, payload, {
    headers: authHeaders(accessToken),
  });
  return data as CommercialConfig;
};

// ── per-tenant per-SKU price overrides (Phase 7 D2) ──────────────────────────
export interface PriceOverride {
  id: string;
  tenant_id: string;
  product_id: string | null;
  component_id: string | null;
  override_margin_pct: number | null;
  override_unit_price: number | null;
}

export const upsertPriceOverride = async (
  accessToken: string,
  tenantId: string,
  payload: {
    product_id?: string;
    component_id?: string;
    override_margin_pct?: number | null;
    override_unit_price?: number | null;
  },
) => {
  const { data } = await api.post(`/pricing/customers/${tenantId}/price-overrides`, payload, {
    headers: authHeaders(accessToken),
  });
  return data as PriceOverride;
};
