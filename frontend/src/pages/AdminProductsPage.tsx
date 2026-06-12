import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Boxes, Building2, ChevronDown, ChevronRight, Landmark, Lock, Percent,
  Plus, Save, Search, Trash2, X,
} from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTenant } from '../context/TenantContext';
import * as productsApi from '../api/productsApi';
import { AdminFinancingPage } from './AdminFinancingPage';
import { extractApiError } from '../utils/extractApiError';
import { toast } from '../utils/toast';
import type { PreviewResult, Product, ProductComponent } from '../types/products';

/** Phase 7 WS6 — one grid of every SKU (manager's columns, per-tenant pricing).
 * Click a row to edit everything EXCEPT vendor / name / area / SKU; the
 * chevron expands read-only component rows inline. Financing & commercial
 * config live on the second tab (D5). */

const PAGE_SIZE = 25;
const FINANCIAL_MODELS = ['CAPEX', 'OPEX', 'BOTH'] as const;
const BILLINGS = ['ONE_TIME', 'RECURRING'] as const;
const UOMS = ['PER_DEVICE', 'PER_LINE', 'PER_SEAT', 'PER_HOUR', 'ONE_TIME', 'PER_DID'] as const;

const money = (v: number | null | undefined): string =>
  v == null ? '—' : `$${Number(v).toFixed(2)}`;
const pct = (v: number | null | undefined): string =>
  v == null ? '—' : `${(Number(v) * 100).toFixed(2)}%`;

const isPapi = (p: Product): boolean =>
  String(p.attributes?.source_type || '').toLowerCase() === 'paapi' || (p.vendor || '').toUpperCase() === 'PAPI';

/** Manager's "Device MRC" / "Per line" columns derive from vendor_cost by uom. */
const deviceMrc = (c: ProductComponent): number | null =>
  c.uom === 'PER_DEVICE' && c.billing === 'RECURRING' ? c.vendor_cost : null;
const perLine = (c: ProductComponent): number | null =>
  c.uom === 'PER_LINE' || c.uom === 'PER_SEAT' || c.uom === 'PER_DID' ? c.vendor_cost : null;

const activeComponents = (p: Product): ProductComponent[] => p.components.filter((c) => c.is_active);

/** Aggregates so the product summary row never shows a wall of dashes. */
const productAggregates = (p: Product) => {
  const comps = activeComponents(p);
  const sum = (fn: (c: ProductComponent) => number | null) =>
    comps.reduce((acc, c) => acc + (Number(fn(c)) || 0), 0);
  return {
    msrp: sum((c) => c.msrp),
    cost: sum((c) => (c.is_required ? c.vendor_cost : 0)),
    mrc: sum((c) => (c.is_required ? deviceMrc(c) : 0)),
    line: sum((c) => perLine(c)),
  };
};

type ComponentDraft = Record<string, string | boolean | null>;

const draftFromComponent = (c: ProductComponent): ComponentDraft => ({
  label: c.label,
  vendor_cost: String(c.vendor_cost ?? ''),
  msrp: c.msrp == null ? '' : String(c.msrp),
  // Per-tenant markup override (Phase 7 D2): starts empty — a value here
  // creates a customer_price_override for the ACTIVE tenant only. The shared
  // catalog margin is never edited from this modal.
  margin_override: '',
  leasing_pct: c.leasing_pct == null ? '' : String(c.leasing_pct),
  financial_model: c.financial_model,
  billing: c.billing,
  interval: c.interval ?? '',
  uom: c.uom,
  default_qty: String(c.default_qty),
  is_required: c.is_required,
  is_active: c.is_active,
});

/** Human-readable diff for the save-confirmation dialog. */
interface SaveSummary {
  tenantChanges: string[];   // apply ONLY to the active tenant
  globalChanges: string[];   // apply to EVERY tenant (shared catalog)
}

const COMPONENT_TYPES = [
  'DEVICE', 'CLOUD_CONTROLLER', 'LINE_CHARGE', 'MANAGED_SERVICE', 'SIM', 'BACKUP_SIM',
  'INSTALLATION', 'PROFESSIONAL_SERVICES', 'MAINTENANCE', 'LICENSE', 'ACCESSORY',
] as const;

const CATEGORIES = [
  'router', 'switch', 'wifi_ap', 'firewall', 'security_appliance', 'cellular_gateway',
  'hotspot', 'laptop', 'tablet', 'phone', 'camera', 'sensor', 'managed_service', 'other',
] as const;

interface NewComponentDraft {
  key: number;
  component_type: string;
  label: string;
  vendor_component_sku: string;
  vendor_cost: string;
  msrp: string;
  billing: string;
  interval: string;
  uom: string;
  default_qty: string;
  is_required: boolean;
}

let nextComponentKey = 1;
const blankNewComponent = (overrides: Partial<NewComponentDraft> = {}): NewComponentDraft => ({
  key: nextComponentKey++,
  component_type: 'DEVICE',
  label: '',
  vendor_component_sku: '',
  vendor_cost: '',
  msrp: '',
  billing: 'ONE_TIME',
  interval: '',
  uom: 'PER_DEVICE',
  default_qty: '1',
  is_required: true,
  ...overrides,
});

const blankNewProduct = () => ({
  vendor: '', technology: '', sku: '', name: '', description: '',
  default_financial_model: 'BOTH', leasing_pct: '0.05', category: 'router',
});

export const AdminProductsPage = () => {
  const { accessToken, user } = useAuth();
  const { activeTenantId, activeTenant } = useTenant();
  const [searchParams, setSearchParams] = useSearchParams();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const canManage = useMemo(
    () => new Set(user?.effective_permissions ?? []).has('manage_pricing'),
    [user?.effective_permissions],
  );

  const tab = searchParams.get('tab') === 'financing' ? 'financing' : 'catalog';
  const setTab = (next: 'catalog' | 'financing') => setSearchParams(next === 'financing' ? { tab: 'financing' } : {});

  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [vendorFilter, setVendorFilter] = useState('');
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [previews, setPreviews] = useState<Record<string, PreviewResult>>({});

  // Tenant-wide markup (D2): empty = inherit the 25% global default.
  const [tenantMargin, setTenantMargin] = useState('');
  const [savingTenantMargin, setSavingTenantMargin] = useState(false);

  // Edit modal (vendor / name / area / SKU are read-only by design).
  const [editing, setEditing] = useState<Product | null>(null);
  const [productDraft, setProductDraft] = useState<Record<string, any>>({});
  const [componentDrafts, setComponentDrafts] = useState<Record<string, ComponentDraft>>({});
  const [overrideDraft, setOverrideDraft] = useState('');
  const [saving, setSaving] = useState(false);
  // Save-confirmation dialogs (the user reviews WHAT changes for WHOM first).
  const [pendingSave, setPendingSave] = useState<SaveSummary | null>(null);
  const [confirmMarkup, setConfirmMarkup] = useState(false);

  // New-product modal (vendor + identity + components, all from here).
  const [creating, setCreating] = useState(false);
  const [newProduct, setNewProduct] = useState(blankNewProduct());
  const [newComponents, setNewComponents] = useState<NewComponentDraft[]>([blankNewComponent()]);
  const [creatingBusy, setCreatingBusy] = useState(false);
  const [createError, setCreateError] = useState('');

  const load = useCallback(async () => {
    if (!accessToken || !isAdmin) return;
    setLoading(true);
    setError('');
    try {
      const rows = await productsApi.listProducts(accessToken, { is_active: true });
      setProducts(rows);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load products'));
    } finally {
      setLoading(false);
    }
  }, [accessToken, isAdmin]);

  useEffect(() => { load(); }, [load]);
  // Server prices per X-Tenant-Id — drop cached previews when the tenant switches.
  useEffect(() => { setPreviews({}); }, [activeTenantId]);

  const vendors = useMemo(
    () => Array.from(new Set(products.map((p) => p.vendor))).sort(),
    [products],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return products.filter((p) => {
      if (vendorFilter && p.vendor !== vendorFilter) return false;
      if (q && ![p.sku, p.name, p.vendor, p.technology].some((v) => (v || '').toLowerCase().includes(q))) return false;
      return true;
    });
  }, [products, search, vendorFilter]);

  useEffect(() => { setPage(1); }, [search, vendorFilter]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageItems = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const loadPreview = useCallback(async (product: Product) => {
    if (!accessToken) return;
    try {
      const preview = await productsApi.componentPreview(accessToken, {
        product_id: product.id, financial_model: 'CAPEX', interval: 'MONTH', selections: {},
      });
      setPreviews((prev) => ({ ...prev, [product.id]: preview }));
    } catch {
      /* preview is best-effort */
    }
  }, [accessToken]);

  const toggleExpand = (product: Product) => {
    const next = expanded === product.id ? null : product.id;
    setExpanded(next);
    if (next && !previews[product.id]) void loadPreview(product);
  };

  const openEditor = (product: Product) => {
    setEditing(product);
    setProductDraft({
      description: product.description ?? '',
      default_financial_model: product.default_financial_model,
      leasing_pct: product.leasing_pct == null ? '' : String(product.leasing_pct),
      is_active: product.is_active,
    });
    setComponentDrafts(Object.fromEntries(product.components.map((c) => [c.id, draftFromComponent(c)])));
    setOverrideDraft('');
    if (!previews[product.id]) void loadPreview(product);
  };

  const doSaveTenantMargin = async () => {
    if (!accessToken || !activeTenantId) return;
    setSavingTenantMargin(true);
    setConfirmMarkup(false);
    try {
      await productsApi.updateCustomerCommercial(accessToken, activeTenantId, {
        default_margin_pct: tenantMargin === '' ? null : Number(tenantMargin),
      });
      toast.success(`Tenant-wide markup for ${activeTenant?.name || 'tenant'} ${tenantMargin === '' ? 'reset to the 25% default' : `set to ${pct(Number(tenantMargin))}`}`);
      setPreviews({});
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to save tenant markup'));
    } finally {
      setSavingTenantMargin(false);
    }
  };

  const num = (v: any): number | null => (v === '' || v == null ? null : Number(v));

  /** Which fields write to the SHARED catalog row (every tenant sees them). */
  const GLOBAL_COMPONENT_FIELDS: [string, string][] = [
    ['label', 'label'], ['vendor_cost', 'cost'], ['msrp', 'MSRP'], ['leasing_pct', 'leasing %'],
    ['billing', 'billing'], ['interval', 'interval'], ['uom', 'UOM'],
    ['default_qty', 'default qty'], ['is_required', 'required'], ['is_active', 'active'],
  ];

  const buildSummary = (): SaveSummary => {
    const tenantName = activeTenant?.name || 'the active tenant';
    const tenantChanges: string[] = [];
    const globalChanges: string[] = [];
    if (!editing) return { tenantChanges, globalChanges };

    if (overrideDraft !== '') {
      tenantChanges.push(`${editing.sku} markup override → ${pct(Number(overrideDraft))} (${tenantName} only)`);
    }
    for (const component of editing.components) {
      const draft = componentDrafts[component.id];
      if (!draft) continue;
      if (draft.margin_override !== '' && draft.margin_override != null) {
        tenantChanges.push(`${component.label}: margin override → ${pct(Number(draft.margin_override))} (${tenantName} only)`);
      }
      const before = draftFromComponent(component);
      for (const [key, labelText] of GLOBAL_COMPONENT_FIELDS) {
        if (draft[key] !== before[key]) {
          globalChanges.push(`${component.label}: ${labelText} ${String(before[key]) || '—'} → ${String(draft[key]) || '—'}`);
        }
      }
    }
    if ((productDraft.description ?? '') !== (editing.description ?? '')) globalChanges.push('Description updated');
    if (productDraft.default_financial_model !== editing.default_financial_model) {
      globalChanges.push(`Financial engagement → ${productDraft.default_financial_model}`);
    }
    const leasingBefore = editing.leasing_pct == null ? '' : String(editing.leasing_pct);
    if (String(productDraft.leasing_pct ?? '') !== leasingBefore) {
      globalChanges.push(`Leasing %ge → ${productDraft.leasing_pct || '—'}`);
    }
    if (Boolean(productDraft.is_active) !== editing.is_active) {
      globalChanges.push(`Product ${productDraft.is_active ? 'activated' : 'deactivated'}`);
    }
    return { tenantChanges, globalChanges };
  };

  const onSaveEditor = () => {
    const summary = buildSummary();
    if (summary.tenantChanges.length === 0 && summary.globalChanges.length === 0) {
      setEditing(null);
      return;
    }
    setPendingSave(summary);
  };

  const doSave = async () => {
    if (!accessToken || !editing) return;
    setSaving(true);
    setError('');
    setPendingSave(null);
    try {
      const papi = isPapi(editing);
      await productsApi.updateProduct(accessToken, editing.id, {
        // vendor / name / technology / sku intentionally NOT sent (read-only).
        // The shared SKU margin is also never touched here — per-tenant
        // markup goes through customer_price_overrides below.
        description: productDraft.description || null,
        default_financial_model: productDraft.default_financial_model,
        leasing_pct: num(productDraft.leasing_pct),
        is_active: Boolean(productDraft.is_active),
      } as Partial<Product>);

      for (const component of editing.components) {
        const draft = componentDrafts[component.id];
        if (!draft) continue;
        const before = draftFromComponent(component);
        const globallyChanged = GLOBAL_COMPONENT_FIELDS.some(([key]) => draft[key] !== before[key]);
        if (globallyChanged) {
          await productsApi.updateComponent(accessToken, component.id, {
            label: String(draft.label || component.label),
            vendor_cost: papi ? undefined : (num(draft.vendor_cost) ?? undefined),
            msrp: num(draft.msrp),
            leasing_pct: num(draft.leasing_pct),
            financial_model: String(draft.financial_model),
            billing: String(draft.billing),
            interval: draft.billing === 'RECURRING' ? (String(draft.interval) || 'MONTH') : null,
            uom: String(draft.uom),
            default_qty: Math.max(1, Number(draft.default_qty) || 1),
            is_required: Boolean(draft.is_required),
            is_active: Boolean(draft.is_active),
          } as Partial<ProductComponent>);
        }
        // Per-tenant component markup → customer_price_overrides for the
        // ACTIVE tenant only. Other tenants are untouched (D2).
        if (!papi && canManage && activeTenantId && draft.margin_override !== '' && draft.margin_override != null) {
          await productsApi.upsertPriceOverride(accessToken, activeTenantId, {
            component_id: component.id,
            override_margin_pct: Number(draft.margin_override),
          });
        }
      }

      if (!papi && canManage && activeTenantId && overrideDraft !== '') {
        await productsApi.upsertPriceOverride(accessToken, activeTenantId, {
          product_id: editing.id,
          override_margin_pct: Number(overrideDraft),
        });
      }

      toast.success(`${editing.sku} saved for ${activeTenant?.name || 'tenant'}`);
      setEditing(null);
      setPreviews({});
      await load();
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to save product'));
    } finally {
      setSaving(false);
    }
  };

  const openCreate = () => {
    setNewProduct(blankNewProduct());
    setNewComponents([blankNewComponent()]);
    setCreateError('');
    setCreating(true);
  };

  const onCreateProduct = async () => {
    if (!accessToken) return;
    setCreateError('');
    for (const field of ['vendor', 'technology', 'sku', 'name'] as const) {
      if (!newProduct[field].trim()) {
        setCreateError(`${field === 'technology' ? 'Area' : field[0].toUpperCase() + field.slice(1)} is required.`);
        return;
      }
    }
    const validComponents = newComponents.filter((c) => c.label.trim() && c.vendor_cost !== '');
    if (validComponents.length === 0) {
      setCreateError('Add at least one component with a label and a cost.');
      return;
    }
    setCreatingBusy(true);
    try {
      const created = await productsApi.createProduct(accessToken, {
        vendor: newProduct.vendor.trim(),
        technology: newProduct.technology.trim(),
        sku: newProduct.sku.trim(),
        name: newProduct.name.trim(),
        description: newProduct.description.trim() || null,
        default_financial_model: newProduct.default_financial_model,
        leasing_pct: newProduct.leasing_pct === '' ? null : Number(newProduct.leasing_pct),
        // margin stays NULL — per-tenant markup rules price it (D2).
        is_active: true,
        attributes: {
          category: newProduct.category,
          product_type: newProduct.category,
          sellable: true,
          source_type: 'manual',
          source_name: 'admin_portal',
        },
      } as any);
      for (const draft of validComponents) {
        await productsApi.addComponent(accessToken, created.id, {
          component_type: draft.component_type,
          label: draft.label.trim(),
          vendor_component_sku: draft.vendor_component_sku.trim() || draft.label.trim().toUpperCase().replace(/\s+/g, '-').slice(0, 32),
          vendor_cost: Number(draft.vendor_cost),
          msrp: draft.msrp === '' ? Number((Number(draft.vendor_cost) * 1.5).toFixed(2)) : Number(draft.msrp),
          billing: draft.billing,
          interval: draft.billing === 'RECURRING' ? (draft.interval || 'MONTH') : null,
          uom: draft.uom,
          default_qty: Math.max(1, Number(draft.default_qty) || 1),
          is_required: draft.is_required,
          is_active: true,
        } as any);
      }
      toast.success(`${created.sku} created with ${validComponents.length} component${validComponents.length === 1 ? '' : 's'}`);
      setCreating(false);
      setPreviews({});
      await load();
      setSearch(created.sku);
    } catch (err: any) {
      setCreateError(extractApiError(err, 'Failed to create product'));
    } finally {
      setCreatingBusy(false);
    }
  };

  if (!isAdmin) {
    return <section className="content-wrap fade-in"><div className="error-text">Admin access required.</div></section>;
  }

  const setComp = (id: string, key: string, value: any) =>
    setComponentDrafts((prev) => ({ ...prev, [id]: { ...prev[id], [key]: value } }));

  const setNewComp = (key: number, field: string, value: any) =>
    setNewComponents((prev) => prev.map((c) => (c.key === key ? { ...c, [field]: value } : c)));

  return (
    <section className="content-wrap fade-in admin-products-page">
      <style>{`
        .apx7-tabs { display: flex; gap: 8px; margin: 4px 0 18px; }
        .apx7-tab { border: 1px solid var(--line); background: var(--card); border-radius: var(--radius-md, 10px);
          padding: 9px 16px; cursor: pointer; font-weight: 600; display: inline-flex; align-items: center; gap: 7px;
          color: var(--muted); font-size: 0.88rem; transition: all 120ms ease; }
        .apx7-tab:hover { background: var(--surface-hover); }
        .apx7-tab.active { background: var(--primary); color: #fff; border-color: var(--primary); }
        .apx7-markup-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 14px 16px;
          margin-bottom: 14px; }
        .apx7-markup-bar strong { font-size: 0.88rem; }
        .apx7-scroll { max-height: 64vh; overflow: auto; border-radius: var(--radius-md, 10px); }
        .apx7-grid { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.82rem; min-width: 1080px; }
        .apx7-grid thead th { position: sticky; top: 0; z-index: 5; background: var(--surface-soft);
          text-align: left; padding: 10px 12px; color: var(--muted); font-weight: 600; font-size: 0.72rem;
          text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap;
          border-bottom: 1px solid var(--line-strong); }
        .apx7-grid td { padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: middle; }
        .apx7-grid .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
        .apx7-prod-row { cursor: pointer; transition: background 100ms ease; }
        .apx7-prod-row:hover { background: var(--surface-hover); }
        .apx7-prod-row td { background: var(--card); }
        .apx7-sku-cell strong { display: block; color: var(--text); font-size: 0.85rem; }
        .apx7-sku-cell .apx7-name { display: block; color: var(--muted); font-size: 0.76rem; max-width: 300px;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 2px; }
        .apx7-chip { display: inline-flex; align-items: center; gap: 4px; font-size: 0.72rem; font-weight: 600;
          border-radius: 999px; padding: 2px 9px; background: var(--soft-pill); color: var(--text); }
        .apx7-papi { background: #fef3c7; color: #92400e; }
        .apx7-comp-row { background: var(--surface-soft); }
        .apx7-comp-row td { background: var(--surface-soft); font-size: 0.79rem; }
        .apx7-comp-row td:first-child { border-left: 3px solid var(--primary-soft); }
        .apx7-comp-label { color: var(--muted); display: block; font-size: 0.73rem; }
        .apx7-pager { display: flex; gap: 8px; align-items: center; justify-content: flex-end; padding: 12px 4px; }
        .apx7-input { width: 86px; padding: 4px 7px; border: 1px solid var(--line); border-radius: 7px;
          background: var(--card); font-size: 0.82rem; }
        .apx7-input:focus { outline: 2px solid var(--primary-soft); border-color: var(--primary); }
        .apx7-tenant-price { color: var(--primary); font-weight: 700; }
        .apx7-papi-note { display: flex; align-items: center; gap: 10px; background: #fef3c7; color: #92400e;
          border-radius: 12px; padding: 12px 16px; font-size: 14px; margin: 14px 0; }

        /* ── edit modal (matches the app's apx/msx modal language) ── */
        .apx7-modal { max-width: 980px; max-height: 88vh; padding: 0; display: flex; flex-direction: column; }
        .apx7-modal-head { padding: 28px 28px 0; }
        .apx7-modal-body { padding: 0 28px; overflow-y: auto; flex: 1; }
        .apx7-modal-foot { padding: 18px 28px 24px; border-top: 1px solid #eef1f6; display: flex;
          align-items: center; gap: 12px; background: #fff; border-radius: 0 0 20px 20px; }
        .apx7-sku-pill { display: inline-flex; align-items: center; gap: 6px; vertical-align: 4px;
          margin-left: 10px; font-size: 13px; font-weight: 700; letter-spacing: 0.02em;
          background: var(--primary-soft); color: var(--primary); border-radius: 999px; padding: 4px 12px; }
        .apx7-identity { display: grid; grid-template-columns: 1fr 1.3fr 0.6fr 2.1fr; gap: 0; overflow: hidden;
          border: 1px solid #e4e8ef; background: var(--surface-soft); border-radius: 14px; margin: 4px 0 20px; }
        .apx7-identity > div { min-width: 0; }
        .apx7-identity > div { padding: 14px 16px; }
        .apx7-identity > div + div { border-left: 1px solid #e4e8ef; }
        .apx7-identity span { display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 700;
          text-transform: uppercase; letter-spacing: 0.06em; color: var(--subtle); margin-bottom: 4px; }
        .apx7-identity strong { font-size: 14.5px; font-weight: 600; color: var(--text); display: block;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .apx7-section { display: flex; align-items: center; gap: 8px; margin: 20px 0 6px; font-size: 12px;
          font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--subtle); }
        .apx7-section::after { content: ''; flex: 1; height: 1px; background: #eef1f6; }
        .apx7-form-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
        .apx7-form-row .apx-field { margin: 0; }
        .apx7-comp-card { border: 1px solid #e4e8ef; border-radius: 14px; padding: 14px 16px; margin: 10px 0;
          transition: border-color 120ms ease, box-shadow 120ms ease; }
        .apx7-comp-card:hover { border-color: var(--line-strong); }
        .apx7-comp-card.off { background: var(--surface-soft); opacity: 0.72; }
        .apx7-comp-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
        .apx7-comp-head input.apx7-label-input { flex: 1; height: 38px; padding: 0 12px; font-size: 14.5px;
          font-weight: 600; color: var(--text); border: 1px solid transparent; border-radius: 9px; background: transparent; }
        .apx7-comp-head input.apx7-label-input:hover { border-color: #e4e8ef; }
        .apx7-comp-head input.apx7-label-input:focus { outline: 2px solid var(--primary); outline-offset: 1px;
          border-color: transparent; background: #fff; }
        .apx7-type-chip { display: inline-flex; align-items: center; font-size: 11px; font-weight: 700;
          letter-spacing: 0.04em; text-transform: uppercase; background: var(--soft-pill); color: #5b6677;
          border-radius: 999px; padding: 4px 11px; white-space: nowrap; }
        .apx7-comp-sku { font-size: 12px; color: var(--subtle); white-space: nowrap; }
        .apx7-mini-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; }
        .apx7-mini { display: flex; flex-direction: column; gap: 4px; }
        .apx7-mini > span { font-size: 11px; font-weight: 700; text-transform: uppercase;
          letter-spacing: 0.05em; color: var(--subtle); }
        .apx7-mini input, .apx7-mini select { height: 38px; padding: 0 10px; border: 1px solid #e4e8ef;
          border-radius: 9px; font-size: 14px; color: var(--text); background: #fff; width: 100%; }
        .apx7-mini input:focus, .apx7-mini select:focus { outline: 2px solid var(--primary);
          outline-offset: 1px; border-color: transparent; }
        .apx7-mini input:disabled, .apx7-mini select:disabled { background: var(--surface-hover);
          color: var(--subtle); cursor: not-allowed; }
        .apx7-toggle-row { display: inline-flex; align-items: center; gap: 8px; font-size: 13px;
          font-weight: 600; color: #5b6677; white-space: nowrap; }
        .apx7-price-tag { margin-left: auto; font-size: 13.5px; font-weight: 700; color: var(--primary);
          white-space: nowrap; }
        .apx7-form-row-3 { grid-template-columns: repeat(3, 1fr); }
        /* two scope zones inside the edit modal */
        .apx7-zone { border: 1px solid #e4e8ef; border-radius: 16px; padding: 16px 18px; margin: 16px 0; }
        .apx7-zone.tenant { border-color: #f2c4dc; background: #fdf6fa; }
        .apx7-zone-head { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 12px;
          padding-bottom: 10px; border-bottom: 1px solid #eef1f6; color: var(--muted); }
        .apx7-zone.tenant .apx7-zone-head { border-bottom-color: #f2c4dc; color: var(--primary); }
        .apx7-zone-head svg { margin-top: 2px; flex: none; }
        .apx7-zone-head strong { display: block; font-size: 14.5px; color: var(--text); }
        .apx7-zone.tenant .apx7-zone-head strong { color: var(--primary); }
        .apx7-zone-head span { display: block; font-size: 12.5px; color: var(--muted); margin-top: 1px; }
        .apx7-ovr-row { display: grid; grid-template-columns: 1fr 130px 130px; gap: 12px; align-items: center;
          padding: 9px 0; border-bottom: 1px dashed #f2c4dc; }
        .apx7-ovr-row:last-child { border-bottom: 0; padding-bottom: 0; }
        .apx7-ovr-product { background: #fff; border: 1px solid #f2c4dc; border-radius: 12px;
          padding: 10px 14px; margin-bottom: 6px; }
        .apx7-ovr-name strong { display: block; font-size: 13.5px; font-weight: 600; color: var(--text); }
        .apx7-ovr-name em { display: block; font-style: normal; font-size: 11.5px; color: var(--muted); }
        .apx7-ovr-current { font-size: 13px; font-weight: 700; color: var(--primary); text-align: right;
          font-variant-numeric: tabular-nums; white-space: nowrap; }
        .apx7-ovr-input { height: 38px; padding: 0 10px; border: 1px solid #f2c4dc; border-radius: 9px;
          font-size: 14px; background: #fff; width: 100%; }
        .apx7-ovr-input:focus { outline: 2px solid var(--primary); outline-offset: 1px; border-color: transparent; }
        .apx7-mini-grid-6 { grid-template-columns: repeat(6, 1fr); }
        .apx7-type-select { height: 38px; padding: 0 10px; border: 1px solid #e4e8ef; border-radius: 9px;
          font-size: 12px; font-weight: 700; letter-spacing: 0.03em; color: #5b6677; background: var(--surface-soft); }
        .apx7-mini-sku { width: 130px; height: 38px; padding: 0 10px; border: 1px solid #e4e8ef;
          border-radius: 9px; font-size: 13px; color: var(--muted); }
        .apx7-tenant-label { color: var(--primary) !important; }
        .apx7-scope-hint { margin: 2px 0 10px; font-size: 13px; color: var(--muted); }
        .apx7-scope-hint strong { color: var(--text); }
        /* confirmation dialog */
        .apx7-confirm { max-width: 560px; padding: 28px; }
        .apx7-confirm-group { border: 1px solid #e4e8ef; border-radius: 12px; padding: 12px 16px; margin: 10px 0; }
        .apx7-confirm-group.tenant { border-color: var(--primary-soft); background: #fdf6fa; }
        .apx7-confirm-group h5 { margin: 0 0 6px; font-size: 12px; font-weight: 700; text-transform: uppercase;
          letter-spacing: 0.06em; color: var(--subtle); display: flex; align-items: center; gap: 6px; }
        .apx7-confirm-group.tenant h5 { color: var(--primary); }
        .apx7-confirm-group ul { margin: 0; padding-left: 18px; font-size: 14px; color: var(--text); }
        .apx7-confirm-group li { margin: 3px 0; }
      `}</style>

      <header className="apx-header">
        <div className="apx-header-text">
          <span className="apx-eyebrow"><Boxes size={15} /> Admin</span>
          <h1>Product catalog &amp; pricing</h1>
          <p className="apx-subtitle">
            One catalog — every SKU and component, priced per tenant. PAPI items resell at PAPI's price (read-only).
          </p>
          <div className="apx-scope">
            <span className="apx-scope-chip"><Building2 size={14} /> Pricing scope: {activeTenant?.name || 'your tenant'}</span>
            <span className="apx-scope-meta">{filtered.length} SKUs · click a row to edit</span>
          </div>
        </div>
        {canManage && tab === 'catalog' && (
          <button className="apx-add-btn" onClick={openCreate}>
            <Plus size={18} /> New product
          </button>
        )}
      </header>

      <div className="apx7-tabs">
        <button className={`apx7-tab ${tab === 'catalog' ? 'active' : ''}`} onClick={() => setTab('catalog')}>
          <Boxes size={15} /> Catalog &amp; markup
        </button>
        <button className={`apx7-tab ${tab === 'financing' ? 'active' : ''}`} onClick={() => setTab('financing')}>
          <Landmark size={15} /> Financing &amp; commercial
        </button>
      </div>

      {tab === 'financing' ? (
        <AdminFinancingPage />
      ) : (
        <>
          {error && <div className="error-text">{error}</div>}

          {canManage && (
            <div className="apx-table-card apx7-markup-bar">
              <Percent size={15} />
              <strong>Tenant-wide markup for {activeTenant?.name || 'this tenant'}</strong>
              <input
                className="apx7-input"
                type="number" step="0.01" min="0" placeholder="0.25"
                value={tenantMargin}
                onChange={(e) => setTenantMargin(e.target.value)}
                aria-label="Tenant-wide markup (decimal)"
              />
              <button className="apx-add-btn" onClick={() => setConfirmMarkup(true)} disabled={savingTenantMargin || !activeTenantId}>
                <Save size={14} /> {savingTenantMargin ? 'Saving…' : 'Apply'}
              </button>
              <span className="apx-scope-meta">Markup on cost (0.20 = 20%). Empty inherits the 25% global default.</span>
            </div>
          )}

          <div className="cat2-bar">
            <div className="cat2-bar-search">
              <Search size={16} />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search SKU, name, vendor…" />
            </div>
            <select value={vendorFilter} onChange={(e) => setVendorFilter(e.target.value)}>
              <option value="">All vendors</option>
              {vendors.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>

          {loading && <div className="cat2-note">Loading catalog…</div>}

          <div className="apx-table-card" style={{ padding: 0 }}>
            <div className="apx7-scroll">
              <table className="apx7-grid">
                <thead>
                  <tr>
                    <th style={{ width: 34 }} />
                    <th>Vendor</th>
                    <th>Area</th>
                    <th>SKU · Product</th>
                    <th>Component Type</th>
                    <th>Fin. Engagement</th>
                    <th className="num">MSRP</th>
                    <th className="num">Extended Price</th>
                    <th className="num">Device MRC</th>
                    <th className="num">Per line</th>
                    <th className="num">Margin %</th>
                    <th className="num">Leasing %ge</th>
                    <th className="num">Tenant price</th>
                  </tr>
                </thead>
                <tbody>
                  {pageItems.map((product) => {
                    const papi = isPapi(product);
                    const open = expanded === product.id;
                    const preview = previews[product.id];
                    const comps = activeComponents(product);
                    const agg = productAggregates(product);
                    return (
                      <Fragment key={product.id}>
                        <tr className="apx7-prod-row" onClick={() => openEditor(product)}>
                          <td onClick={(e) => { e.stopPropagation(); toggleExpand(product); }}
                              role="button" aria-label={`Expand ${product.sku}`}>
                            {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                          </td>
                          <td><span className="apx7-chip">{product.vendor}</span></td>
                          <td>{product.technology}</td>
                          <td className="apx7-sku-cell">
                            <strong>{product.sku} {papi && <span className="apx7-chip apx7-papi"><Lock size={9} /> PAPI</span>}</strong>
                            <span className="apx7-name" title={product.name}>{product.name}</span>
                          </td>
                          <td>{comps.length} component{comps.length === 1 ? '' : 's'}</td>
                          <td>{product.default_financial_model}</td>
                          <td className="num">{money(agg.msrp)}</td>
                          <td className="num">{money(agg.cost)}</td>
                          <td className="num">{money(agg.mrc)}</td>
                          <td className="num">{agg.line > 0 ? money(agg.line) : money(0)}</td>
                          <td className="num">{papi ? pct(0) : pct(product.margin_pct ?? 0.25)}</td>
                          <td className="num">{pct(product.leasing_pct ?? 0)}</td>
                          <td className="num apx7-tenant-price">
                            {preview
                              ? <>{money(preview.one_time_total)}{Number(preview.monthly_total) > 0 && <> + {money(preview.monthly_total)}/mo</>}</>
                              : open ? '…' : ''}
                          </td>
                        </tr>
                        {open && comps.map((component) => {
                          const previewLine = preview?.lines?.find((l) => l.component_id === component.id);
                          return (
                            <tr key={component.id} className="apx7-comp-row">
                              <td />
                              <td />
                              <td />
                              <td className="apx7-sku-cell">
                                <strong>{component.vendor_component_sku || product.sku}</strong>
                                <span className="apx7-comp-label">{component.label}</span>
                              </td>
                              <td>{component.component_type.replace(/_/g, ' ')}{component.is_required ? '' : ' · optional'}</td>
                              <td>{component.financial_model}</td>
                              <td className="num">{money(component.msrp)}</td>
                              <td className="num">{money(component.vendor_cost)}</td>
                              <td className="num">{money(deviceMrc(component) ?? 0)}</td>
                              <td className="num">{money(perLine(component) ?? 0)}</td>
                              <td className="num">{papi ? pct(0) : pct(component.margin_pct ?? product.margin_pct ?? 0.25)}</td>
                              <td className="num">{pct(component.leasing_pct ?? product.leasing_pct ?? 0)}</td>
                              <td className="num apx7-tenant-price">
                                {previewLine
                                  ? `${money(previewLine.unit_price)}${previewLine.billing === 'RECURRING' ? '/mo' : ''}`
                                  : money(0)}
                              </td>
                            </tr>
                          );
                        })}
                      </Fragment>
                    );
                  })}
                  {!loading && pageItems.length === 0 && (
                    <tr><td colSpan={13} className="apx-empty">No products matched.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {pageCount > 1 && (
              <div className="apx7-pager">
                <button className="apx-ghost-btn" disabled={safePage <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
                <span className="apx-scope-meta">Page {safePage} of {pageCount}</span>
                <button className="apx-ghost-btn" disabled={safePage >= pageCount} onClick={() => setPage((p) => p + 1)}>Next</button>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Edit modal — vendor / name / area / SKU locked ── */}
      {editing && (
        <div className="apx-modal-overlay" onClick={() => setEditing(null)}>
          <div className="apx-modal apx7-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setEditing(null)}><X size={18} /></button>

            <div className="apx7-modal-head">
              <h3 className="apx-modal-title">
                Edit product
                <span className="apx7-sku-pill">{editing.sku}</span>
                {isPapi(editing) && <span className="apx7-sku-pill" style={{ background: '#fef3c7', color: '#92400e' }}><Lock size={11} /> PAPI-priced</span>}
              </h3>
              <p className="apx-modal-sub">
                Pricing, billing and component setup — identity fields are locked.
                {previews[editing.id] && (
                  <> Currently <span className="apx7-tenant-price">
                    {money(previews[editing.id].one_time_total)}
                    {Number(previews[editing.id].monthly_total) > 0 && <> + {money(previews[editing.id].monthly_total)}/mo</>}
                  </span> for {activeTenant?.name || 'this tenant'}.</>
                )}
              </p>
            </div>

            <div className="apx7-modal-body">
              <div className="apx7-identity">
                <div><span><Lock size={10} /> Vendor</span><strong>{editing.vendor}</strong></div>
                <div><span><Lock size={10} /> Area</span><strong>{editing.technology}</strong></div>
                <div><span><Lock size={10} /> SKU</span><strong>{editing.sku}</strong></div>
                <div><span><Lock size={10} /> Name</span><strong title={editing.name}>{editing.name}</strong></div>
              </div>

              {isPapi(editing) && (
                <div className="apx7-papi-note">
                  <Lock size={15} /> PAPI-sourced — resold at PAPI's exact price for every tenant. Cost, margin and markup fields are locked.
                </div>
              )}

              {/* ── ZONE 1 · per-tenant pricing — affects ONLY the active tenant ── */}
              {canManage && !isPapi(editing) && (
                <div className="apx7-zone tenant">
                  <div className="apx7-zone-head">
                    <Building2 size={15} />
                    <div>
                      <strong>Pricing for {activeTenant?.name || 'this tenant'}</strong>
                      <span>Markup overrides — saved as overrides for {activeTenant?.name || 'this tenant'} only. No other tenant is affected.</span>
                    </div>
                  </div>
                  <div className="apx7-ovr-row apx7-ovr-product">
                    <span className="apx7-ovr-name"><strong>Whole product markup</strong><em>beats the tenant-wide default for this SKU</em></span>
                    <span className="apx7-ovr-current">
                      {previews[editing.id]
                        ? <>{money(previews[editing.id].one_time_total)}{Number(previews[editing.id].monthly_total) > 0 && <> + {money(previews[editing.id].monthly_total)}/mo</>}</>
                        : '…'}
                    </span>
                    <input className="apx7-ovr-input" type="number" step="0.01" min="0" placeholder="e.g. 0.30"
                           aria-label={`Markup override for ${editing.sku}`}
                           value={overrideDraft}
                           onChange={(e) => setOverrideDraft(e.target.value)} />
                  </div>
                  {editing.components.filter((c) => c.is_active).map((component) => {
                    const draft = componentDrafts[component.id] || draftFromComponent(component);
                    const previewLine = previews[editing.id]?.lines?.find((l) => l.component_id === component.id);
                    return (
                      <div key={`ovr-${component.id}`} className="apx7-ovr-row">
                        <span className="apx7-ovr-name">
                          <strong>{component.label}</strong>
                          <em>{component.component_type.replace(/_/g, ' ').toLowerCase()} · currently {previewLine ? `${pct(previewLine.margin_pct)} (${previewLine.margin_source.replace(/_/g, ' ')})` : 'inherits'}</em>
                        </span>
                        <span className="apx7-ovr-current">
                          {previewLine ? `${money(previewLine.unit_price)}${previewLine.billing === 'RECURRING' ? '/mo' : ''}` : '—'}
                        </span>
                        <input className="apx7-ovr-input" type="number" step="0.01" min="0"
                               placeholder={previewLine ? pct(previewLine.margin_pct) : 'inherit'}
                               aria-label={`Margin override for ${component.label}`}
                               value={String(draft.margin_override ?? '')}
                               onChange={(e) => setComp(component.id, 'margin_override', e.target.value)} />
                      </div>
                    );
                  })}
                </div>
              )}

              {/* ── ZONE 2 · shared catalog — affects EVERY tenant ── */}
              <div className="apx7-zone">
                <div className="apx7-zone-head">
                  <Boxes size={15} />
                  <div>
                    <strong>Shared catalog</strong>
                    <span>Costs, MSRP, billing &amp; structure — one catalog, so these change for <strong>every tenant</strong>.</span>
                  </div>
                </div>

                <div className="apx7-form-row apx7-form-row-3">
                  <label className="apx-field">
                    <span>Financial engagement</span>
                    <select value={productDraft.default_financial_model}
                            onChange={(e) => setProductDraft({ ...productDraft, default_financial_model: e.target.value })}>
                      {FINANCIAL_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </label>
                  <label className="apx-field">
                    <span>Leasing %ge (decimal)</span>
                    <input type="number" step="0.01" min="0" placeholder="—"
                           value={productDraft.leasing_pct}
                           onChange={(e) => setProductDraft({ ...productDraft, leasing_pct: e.target.value })} />
                  </label>
                  <label className="apx-field">
                    <span>Description</span>
                    <input value={productDraft.description}
                           onChange={(e) => setProductDraft({ ...productDraft, description: e.target.value })} />
                  </label>
                </div>

                {editing.components.map((component) => {
                  const draft = componentDrafts[component.id] || draftFromComponent(component);
                  const papi = isPapi(editing);
                  const previewLine = previews[editing.id]?.lines?.find((l) => l.component_id === component.id);
                  return (
                    <div key={component.id} className={`apx7-comp-card${draft.is_active ? '' : ' off'}`}>
                      <div className="apx7-comp-head">
                        <span className="apx7-type-chip">{component.component_type.replace(/_/g, ' ')}</span>
                        <input
                          className="apx7-label-input"
                          value={String(draft.label ?? '')}
                          aria-label={`Label for ${component.vendor_component_sku}`}
                          onChange={(e) => setComp(component.id, 'label', e.target.value)}
                        />
                        <span className="apx7-comp-sku">{component.vendor_component_sku}</span>
                        {previewLine && (
                          <span className="apx7-price-tag">
                            {money(previewLine.unit_price)}{previewLine.billing === 'RECURRING' ? '/mo' : ''}
                          </span>
                        )}
                      </div>
                      <div className="apx7-mini-grid apx7-mini-grid-6">
                        <label className="apx7-mini">
                          <span>Cost</span>
                          <input type="number" step="0.01" disabled={papi} value={String(draft.vendor_cost ?? '')}
                                 onChange={(e) => setComp(component.id, 'vendor_cost', e.target.value)} />
                        </label>
                        <label className="apx7-mini">
                          <span>MSRP</span>
                          <input type="number" step="0.01" value={String(draft.msrp ?? '')}
                                 onChange={(e) => setComp(component.id, 'msrp', e.target.value)} />
                        </label>
                        <label className="apx7-mini">
                          <span>Leasing</span>
                          <input type="number" step="0.01" placeholder="—" value={String(draft.leasing_pct ?? '')}
                                 onChange={(e) => setComp(component.id, 'leasing_pct', e.target.value)} />
                        </label>
                        <label className="apx7-mini">
                          <span>Billing</span>
                          <select value={String(draft.billing)} onChange={(e) => setComp(component.id, 'billing', e.target.value)}>
                            {BILLINGS.map((b) => <option key={b} value={b}>{b === 'ONE_TIME' ? 'One-time' : 'Recurring'}</option>)}
                          </select>
                        </label>
                        <label className="apx7-mini">
                          <span>UOM</span>
                          <select value={String(draft.uom)} onChange={(e) => setComp(component.id, 'uom', e.target.value)}>
                            {UOMS.map((u) => <option key={u} value={u}>{u.replace(/_/g, ' ').toLowerCase()}</option>)}
                          </select>
                        </label>
                        <div className="apx7-mini">
                          <span>Qty</span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <input type="number" min="1" style={{ width: 58 }} value={String(draft.default_qty ?? '1')}
                                   aria-label="Default quantity"
                                   onChange={(e) => setComp(component.id, 'default_qty', e.target.value)} />
                            <span className="apx7-toggle-row">
                              <button type="button" className={`amx-toggle ${draft.is_required ? 'on' : ''}`}
                                      role="switch" aria-checked={Boolean(draft.is_required)} aria-label="Required"
                                      onClick={() => setComp(component.id, 'is_required', !draft.is_required)} />
                              Req.
                            </span>
                            <span className="apx7-toggle-row">
                              <button type="button" className={`amx-toggle ${draft.is_active ? 'on' : ''}`}
                                      role="switch" aria-checked={Boolean(draft.is_active)} aria-label="Active"
                                      onClick={() => setComp(component.id, 'is_active', !draft.is_active)} />
                              Active
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="apx7-modal-foot">
              <span className="apx7-toggle-row" style={{ marginRight: 'auto' }}>
                <button type="button" className={`amx-toggle ${productDraft.is_active ? 'on' : ''}`}
                        role="switch" aria-checked={Boolean(productDraft.is_active)} aria-label="Product active"
                        onClick={() => setProductDraft({ ...productDraft, is_active: !productDraft.is_active })} />
                Product active
              </span>
              <button className="apx-ghost-btn" onClick={() => setEditing(null)}>Cancel</button>
              <button className="apx-add-btn" onClick={onSaveEditor} disabled={saving || !canManage}>
                <Save size={15} /> {saving ? 'Saving…' : 'Review & save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── new product — vendor, identity & components in one flow ── */}
      {creating && (
        <div className="apx-modal-overlay" onClick={() => setCreating(false)}>
          <div className="apx-modal apx7-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setCreating(false)}><X size={18} /></button>

            <div className="apx7-modal-head">
              <h3 className="apx-modal-title">New product</h3>
              <p className="apx-modal-sub">
                Lands in the shared catalog for every tenant, priced by each tenant's markup
                (25% default). New vendors are created just by typing their name.
              </p>
            </div>

            <div className="apx7-modal-body">
              {createError && <div className="error-text" style={{ marginBottom: 10 }}>{createError}</div>}

              <div className="apx7-section">Identity</div>
              <div className="apx7-form-row">
                <label className="apx-field">
                  <span>Vendor</span>
                  <input list="apx7-vendors" placeholder="e.g. Meraki or a new vendor"
                         value={newProduct.vendor}
                         onChange={(e) => setNewProduct({ ...newProduct, vendor: e.target.value })} />
                  <datalist id="apx7-vendors">
                    {vendors.map((v) => <option key={v} value={v} />)}
                  </datalist>
                </label>
                <label className="apx-field">
                  <span>Area / technology</span>
                  <input placeholder="e.g. POTS / Cellular Router"
                         value={newProduct.technology}
                         onChange={(e) => setNewProduct({ ...newProduct, technology: e.target.value })} />
                </label>
                <label className="apx-field">
                  <span>SKU</span>
                  <input placeholder="unique, e.g. 90X3"
                         value={newProduct.sku}
                         onChange={(e) => setNewProduct({ ...newProduct, sku: e.target.value })} />
                </label>
                <label className="apx-field">
                  <span>Catalog category</span>
                  <select value={newProduct.category}
                          onChange={(e) => setNewProduct({ ...newProduct, category: e.target.value })}>
                    {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
                  </select>
                </label>
              </div>
              <label className="apx-field">
                <span>Product name</span>
                <input placeholder="Full display name shown in the customer catalog"
                       value={newProduct.name}
                       onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })} />
              </label>
              <label className="apx-field">
                <span>Description</span>
                <input placeholder="Optional"
                       value={newProduct.description}
                       onChange={(e) => setNewProduct({ ...newProduct, description: e.target.value })} />
              </label>

              <div className="apx7-section">Commercial</div>
              <div className="apx7-form-row apx7-form-row-3">
                <label className="apx-field">
                  <span>Financial engagement</span>
                  <select value={newProduct.default_financial_model}
                          onChange={(e) => setNewProduct({ ...newProduct, default_financial_model: e.target.value })}>
                    {FINANCIAL_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </label>
                <label className="apx-field">
                  <span>Leasing %ge (decimal)</span>
                  <input type="number" step="0.01" min="0"
                         value={newProduct.leasing_pct}
                         onChange={(e) => setNewProduct({ ...newProduct, leasing_pct: e.target.value })} />
                </label>
                <div className="apx-field">
                  <span>Markup</span>
                  <p className="apx7-scope-hint" style={{ margin: '10px 0 0' }}>
                    Inherits each tenant's markup (25% default) — set overrides after creating.
                  </p>
                </div>
              </div>

              <div className="apx7-section">Components</div>
              <p className="apx7-scope-hint">
                At least one priced component. MSRP defaults to 1.5× cost when left empty.
              </p>
              {newComponents.map((draft) => (
                <div key={draft.key} className="apx7-comp-card">
                  <div className="apx7-comp-head">
                    <select className="apx7-type-select" value={draft.component_type}
                            aria-label="Component type"
                            onChange={(e) => setNewComp(draft.key, 'component_type', e.target.value)}>
                      {COMPONENT_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
                    </select>
                    <input className="apx7-label-input" placeholder="Component label (e.g. Device, Voice Line…)"
                           value={draft.label}
                           onChange={(e) => setNewComp(draft.key, 'label', e.target.value)} />
                    <input className="apx7-mini-sku" placeholder="vendor SKU"
                           aria-label="Vendor component SKU"
                           value={draft.vendor_component_sku}
                           onChange={(e) => setNewComp(draft.key, 'vendor_component_sku', e.target.value)} />
                    {newComponents.length > 1 && (
                      <button className="apx-modal-close" style={{ position: 'static' }} aria-label="Remove component"
                              onClick={() => setNewComponents((prev) => prev.filter((c) => c.key !== draft.key))}>
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                  <div className="apx7-mini-grid">
                    <label className="apx7-mini">
                      <span>Cost</span>
                      <input type="number" step="0.01" min="0" placeholder="0.00" value={draft.vendor_cost}
                             onChange={(e) => setNewComp(draft.key, 'vendor_cost', e.target.value)} />
                    </label>
                    <label className="apx7-mini">
                      <span>MSRP</span>
                      <input type="number" step="0.01" min="0" placeholder="1.5× cost" value={draft.msrp}
                             onChange={(e) => setNewComp(draft.key, 'msrp', e.target.value)} />
                    </label>
                    <label className="apx7-mini">
                      <span>Billing</span>
                      <select value={draft.billing} onChange={(e) => setNewComp(draft.key, 'billing', e.target.value)}>
                        {BILLINGS.map((b) => <option key={b} value={b}>{b === 'ONE_TIME' ? 'One-time' : 'Recurring'}</option>)}
                      </select>
                    </label>
                    <label className="apx7-mini">
                      <span>Interval</span>
                      <select value={draft.interval} disabled={draft.billing !== 'RECURRING'}
                              onChange={(e) => setNewComp(draft.key, 'interval', e.target.value)}>
                        <option value="">—</option>
                        <option value="MONTH">Monthly</option>
                        <option value="YEAR">Annual</option>
                      </select>
                    </label>
                    <label className="apx7-mini">
                      <span>UOM</span>
                      <select value={draft.uom} onChange={(e) => setNewComp(draft.key, 'uom', e.target.value)}>
                        {UOMS.map((u) => <option key={u} value={u}>{u.replace(/_/g, ' ').toLowerCase()}</option>)}
                      </select>
                    </label>
                    <label className="apx7-mini">
                      <span>Qty</span>
                      <input type="number" min="1" value={draft.default_qty}
                             onChange={(e) => setNewComp(draft.key, 'default_qty', e.target.value)} />
                    </label>
                    <div className="apx7-mini">
                      <span>Required</span>
                      <span className="apx7-toggle-row" style={{ paddingTop: 6 }}>
                        <button type="button" className={`amx-toggle ${draft.is_required ? 'on' : ''}`}
                                role="switch" aria-checked={draft.is_required} aria-label="Required"
                                onClick={() => setNewComp(draft.key, 'is_required', !draft.is_required)} />
                        {draft.is_required ? 'Required' : 'Optional'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
              <button className="apx-ghost-btn" style={{ margin: '4px 0 16px' }}
                      onClick={() => setNewComponents((prev) => [...prev, blankNewComponent({ component_type: 'MANAGED_SERVICE', billing: 'RECURRING', interval: 'MONTH', is_required: false })])}>
                <Plus size={14} /> Add component
              </button>
            </div>

            <div className="apx7-modal-foot">
              <button className="apx-ghost-btn" style={{ marginLeft: 'auto' }} onClick={() => setCreating(false)}>Cancel</button>
              <button className="apx-add-btn" onClick={onCreateProduct} disabled={creatingBusy}>
                <Plus size={15} /> {creatingBusy ? 'Creating…' : 'Create product'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── save confirmation — spells out the scope of every change ── */}
      {pendingSave && editing && (
        <div className="apx-modal-overlay" onClick={() => setPendingSave(null)}>
          <div className="apx-modal apx7-confirm" role="alertdialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setPendingSave(null)}><X size={18} /></button>
            <h3 className="apx-modal-title">Confirm pricing changes</h3>
            <p className="apx-modal-sub">
              You are editing <strong>{editing.sku}</strong> while scoped to{' '}
              <strong className="apx7-tenant-label">{activeTenant?.name || 'your tenant'}</strong>. Review what applies where:
            </p>

            {pendingSave.tenantChanges.length > 0 && (
              <div className="apx7-confirm-group tenant">
                <h5><Building2 size={12} /> Only for {activeTenant?.name || 'this tenant'}</h5>
                <ul>{pendingSave.tenantChanges.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            )}
            {pendingSave.globalChanges.length > 0 && (
              <div className="apx7-confirm-group">
                <h5><Boxes size={12} /> Shared catalog — affects EVERY tenant</h5>
                <ul>{pendingSave.globalChanges.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            )}

            <div className="apx-modal-foot">
              <button className="apx-ghost-btn" onClick={() => setPendingSave(null)}>Back</button>
              <button className="apx-add-btn" onClick={doSave} disabled={saving}>
                <Save size={15} /> {saving ? 'Saving…' : 'Confirm & save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── tenant-wide markup confirmation ── */}
      {confirmMarkup && (
        <div className="apx-modal-overlay" onClick={() => setConfirmMarkup(false)}>
          <div className="apx-modal apx7-confirm" role="alertdialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setConfirmMarkup(false)}><X size={18} /></button>
            <h3 className="apx-modal-title">Confirm tenant-wide markup</h3>
            <p className="apx-modal-sub">
              {tenantMargin === ''
                ? <>Reset the markup for <strong className="apx7-tenant-label">{activeTenant?.name || 'this tenant'}</strong> to inherit the <strong>25% global default</strong>?</>
                : <>Set the markup for <strong className="apx7-tenant-label">{activeTenant?.name || 'this tenant'}</strong> to <strong>{pct(Number(tenantMargin))}</strong>?</>}
            </p>
            <div className="apx7-confirm-group tenant">
              <h5><Building2 size={12} /> Only for {activeTenant?.name || 'this tenant'}</h5>
              <ul>
                <li>Every SKU without its own override reprices to cost × {tenantMargin === '' ? '1.25 (default)' : `${(1 + Number(tenantMargin)).toFixed(2)}`}.</li>
                <li>No other tenant is affected.</li>
              </ul>
            </div>
            <div className="apx-modal-foot">
              <button className="apx-ghost-btn" onClick={() => setConfirmMarkup(false)}>Back</button>
              <button className="apx-add-btn" onClick={doSaveTenantMargin} disabled={savingTenantMargin}>
                <Save size={15} /> {savingTenantMargin ? 'Saving…' : 'Confirm & apply'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
