import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Boxes, Building2, Calculator, DollarSign, Download, Pencil, Plus, Save, Search, Server, X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import * as productsApi from '../api/productsApi';
import * as commerceApi from '../api/commerceApi';
import { extractApiError } from '../utils/extractApiError';
import {
  COMPONENT_TYPES,
  type Product,
  type ProductComponent,
  type PreviewResult,
} from '../types/products';
import type { CatalogItem } from '../types/commerce';

const FINANCIAL_MODELS = ['CAPEX', 'OPEX', 'BOTH'] as const;
const UOMS = ['PER_DEVICE', 'PER_LINE', 'PER_SEAT', 'PER_HOUR', 'ONE_TIME', 'PER_DID'] as const;

const blankProduct = {
  vendor: '', technology: '', sku: '', name: '',
  default_financial_model: 'BOTH', margin_pct: '', leasing_pct: '',
};

const blankComponent = {
  component_type: 'DEVICE', label: '', vendor_component_sku: '', vendor_cost: '',
  msrp: '', uom: 'PER_DEVICE', billing: 'ONE_TIME', interval: '', margin_pct: '',
  is_required: true, is_active: true,
};

const money = (value: number | null | undefined, cents = true): string =>
  '$' + new Intl.NumberFormat('en-US', {
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: cents ? 2 : 0,
  }).format(value || 0);

const statusInfo = (item: CatalogItem): { label: string; tone: string } => {
  if (item.is_active === false) return { label: 'Inactive', tone: 'inactive' };
  const a = (item.availability || 'in_stock').toLowerCase();
  if (a.includes('back')) return { label: 'Backorder', tone: 'backorder' };
  if (a.includes('lead')) return { label: 'Lead time', tone: 'backorder' };
  return { label: 'Active', tone: 'active' };
};

const csvCell = (value: string | number): string => {
  const str = String(value ?? '');
  return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
};

export const AdminProductsPage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const canManage = useMemo(
    () => new Set(user?.effective_permissions ?? []).has('manage_products'),
    [user?.effective_permissions],
  );

  // ── catalog (the unified product list shown on the page) ───────────────
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [orgName, setOrgName] = useState<string>('');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [filterOpen, setFilterOpen] = useState(false);

  // ── managed-rate inline editor (row pencil) ────────────────────────────
  const [rateItem, setRateItem] = useState<CatalogItem | null>(null);
  const [rateValue, setRateValue] = useState('');
  const [savingRate, setSavingRate] = useState(false);

  // ── product/component editor (existing CRUD, now in a modal) ───────────
  const [editorOpen, setEditorOpen] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [selected, setSelected] = useState<Product | null>(null);
  const [newProduct, setNewProduct] = useState<Record<string, any>>({ ...blankProduct });
  const [newComponent, setNewComponent] = useState<Record<string, any>>({ ...blankComponent });
  const [previewModel, setPreviewModel] = useState('CAPEX');
  const [previewInterval, setPreviewInterval] = useState('MONTH');
  const [selections, setSelections] = useState<Record<string, number>>({});
  const [preview, setPreview] = useState<PreviewResult | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    if (!accessToken || !isAdmin) return;
    setLoading(true);
    setError('');
    try {
      const [catalogRows, productRows, profile] = await Promise.all([
        commerceApi.getCatalog(accessToken, { type: 'DEVICE', sort: 'recommended', page_size: 250 }),
        productsApi.listProducts(accessToken),
        commerceApi.getOnboardingProfile(accessToken).catch(() => null),
      ]);
      setCatalog(catalogRows);
      setProducts(productRows);
      setOrgName(profile?.organization_name || '');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load products'));
    } finally {
      setLoading(false);
    }
  }, [accessToken, isAdmin]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(''), 2500);
    return () => window.clearTimeout(t);
  }, [notice]);

  // ── derived stats (all from real catalog data) ─────────────────────────
  const stats = useMemo(() => {
    const vendors = new Set(catalog.map((c) => c.vendor).filter(Boolean));
    const withManaged = catalog.filter((c) => c.managed_service_price != null);
    const avgPrice = catalog.length
      ? catalog.reduce((sum, c) => sum + (c.price || 0), 0) / catalog.length
      : 0;
    return {
      devices: catalog.length,
      vendors: vendors.size,
      avgPrice,
      managed: withManaged.length,
    };
  }, [catalog]);

  const filteredCatalog = useMemo(() => {
    const q = query.trim().toLowerCase();
    return catalog.filter((item) => {
      if (statusFilter !== 'all' && statusInfo(item).tone !== statusFilter) return false;
      if (!q) return true;
      return [item.name, item.sku, item.vendor].some((v) => (v || '').toLowerCase().includes(q));
    });
  }, [catalog, query, statusFilter]);

  const exportCsv = () => {
    const header = ['Product', 'SKU', 'Vendor', 'List price', 'Managed/mo', 'Status'];
    const lines = [header.join(',')].concat(
      filteredCatalog.map((c) => [
        c.name, c.sku, c.vendor || '',
        (c.price || 0).toFixed(2),
        c.managed_service_price != null ? c.managed_service_price.toFixed(2) : '',
        statusInfo(c).label,
      ].map(csvCell).join(',')),
    );
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'products-pricing.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const openRateEditor = (item: CatalogItem) => {
    setRateItem(item);
    setRateValue(item.managed_service_price != null ? String(item.managed_service_price) : '');
  };

  const saveRate = async () => {
    if (!rateItem || !accessToken) return;
    setSavingRate(true);
    setError('');
    try {
      const value = rateValue.trim() === '' ? null : Number(rateValue);
      const updated = await commerceApi.updateDeviceManagedServicePrice(accessToken, rateItem.id, value);
      setCatalog((rows) => rows.map((r) => (r.id === rateItem.id ? { ...r, managed_service_price: updated.managed_service_price } : r)));
      setNotice(`Updated managed rate for ${rateItem.name}`);
      setRateItem(null);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to update managed-service rate'));
    } finally {
      setSavingRate(false);
    }
  };

  // ── existing product/component CRUD handlers (unchanged) ───────────────
  const num = (v: any) => (v === '' || v === null || v === undefined ? null : Number(v));

  const selectProduct = async (id: string) => {
    if (!accessToken) return;
    setError('');
    setPreview(null);
    setSelections({});
    try {
      setSelected(await productsApi.getProduct(accessToken, id));
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load product'));
    }
  };

  const refreshProducts = async () => {
    if (!accessToken) return;
    try { setProducts(await productsApi.listProducts(accessToken)); } catch { /* noop */ }
  };

  const onCreateProduct = async () => {
    if (!accessToken) return;
    try {
      const payload: any = {
        vendor: newProduct.vendor, technology: newProduct.technology, sku: newProduct.sku,
        name: newProduct.name, default_financial_model: newProduct.default_financial_model,
        margin_pct: num(newProduct.margin_pct), leasing_pct: num(newProduct.leasing_pct),
      };
      Object.keys(payload).forEach((k) => payload[k] === null && delete payload[k]);
      const created = await productsApi.createProduct(accessToken, payload);
      setNewProduct({ ...blankProduct });
      setNotice(`Created ${created.sku}`);
      await refreshProducts();
      await selectProduct(created.id);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to create product'));
    }
  };

  const onSaveComponentRow = async (c: ProductComponent) => {
    if (!accessToken) return;
    try {
      await productsApi.updateComponent(accessToken, c.id, {
        vendor_cost: c.vendor_cost, msrp: c.msrp, margin_pct: c.margin_pct, leasing_pct: c.leasing_pct,
        billing: c.billing, interval: c.interval || null, uom: c.uom, default_qty: c.default_qty,
        is_required: c.is_required, is_active: c.is_active, label: c.label,
      });
      setNotice(`Saved ${c.label}`);
      if (selected) await selectProduct(selected.id);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to save component'));
    }
  };

  const onAddComponent = async () => {
    if (!selected || !accessToken) return;
    try {
      const payload: any = {
        component_type: newComponent.component_type, label: newComponent.label,
        vendor_component_sku: newComponent.vendor_component_sku || null,
        vendor_cost: num(newComponent.vendor_cost) ?? 0, msrp: num(newComponent.msrp),
        uom: newComponent.uom, billing: newComponent.billing,
        interval: newComponent.interval || null, margin_pct: num(newComponent.margin_pct),
        is_required: newComponent.is_required, is_active: newComponent.is_active,
      };
      await productsApi.addComponent(accessToken, selected.id, payload);
      setNewComponent({ ...blankComponent });
      setNotice('Component added');
      await selectProduct(selected.id);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to add component'));
    }
  };

  const patchComponentLocal = (id: string, field: keyof ProductComponent, value: any) => {
    setSelected((prev) =>
      prev ? { ...prev, components: prev.components.map((c) => (c.id === id ? { ...c, [field]: value } : c)) } : prev,
    );
  };

  const runPreview = async () => {
    if (!selected || !accessToken) return;
    try {
      setPreview(await productsApi.componentPreview(accessToken, {
        product_id: selected.id, financial_model: previewModel, interval: previewInterval, selections,
      }));
    } catch (err: any) {
      setError(extractApiError(err, 'Preview failed'));
    }
  };

  if (!isAdmin) {
    return <section className="content-wrap fade-in"><div className="error-text">Admin access required.</div></section>;
  }

  return (
    <section className="content-wrap fade-in admin-products-page">
      <header className="apx-header">
        <div className="apx-header-text">
          <span className="apx-eyebrow"><Server size={15} /> Admin</span>
          <h1>Products &amp; pricing</h1>
          <p className="apx-subtitle">Manage the unified catalog, list prices, and managed-service rates.</p>
          <div className="apx-scope">
            <span className="apx-scope-chip"><Building2 size={14} /> Scope: {orgName || 'All tenants'}</span>
            <span className="apx-scope-meta">
              {stats.devices} devices · {stats.vendors} vendor{stats.vendors === 1 ? '' : 's'}
            </span>
          </div>
        </div>
        {canManage && (
          <button className="apx-add-btn" onClick={() => setEditorOpen(true)}>
            <Plus size={18} /> Add product
          </button>
        )}
      </header>

      {error && <div className="error-text">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}

      <div className="apx-stats">
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Devices in scope</span><span className="apx-stat-icon blue"><Server size={16} /></span></div>
          <div className="apx-stat-value">{stats.devices}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Active vendors</span><span className="apx-stat-icon violet"><Building2 size={16} /></span></div>
          <div className="apx-stat-value">{stats.vendors}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Avg. list price</span><span className="apx-stat-icon green"><DollarSign size={16} /></span></div>
          <div className="apx-stat-value">{money(stats.avgPrice, false)}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Managed SKUs</span><span className="apx-stat-icon amber"><Boxes size={16} /></span></div>
          <div className="apx-stat-value">{stats.managed}</div>
        </article>
      </div>

      <div className="apx-table-card">
        <div className="apx-table-toolbar">
          <div className="apx-search">
            <Search size={16} />
            <input
              placeholder="Search products & SKUs…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="apx-toolbar-actions">
            <div className="apx-filter-wrap">
              <button className="apx-tool-btn" onClick={() => setFilterOpen((v) => !v)}>
                <span className="apx-filter-icon" /> Filter
              </button>
              {filterOpen && (
                <div className="apx-filter-menu" onMouseLeave={() => setFilterOpen(false)}>
                  {[
                    { key: 'all', label: 'All statuses' },
                    { key: 'active', label: 'Active' },
                    { key: 'backorder', label: 'Backorder' },
                    { key: 'inactive', label: 'Inactive' },
                  ].map((opt) => (
                    <button
                      key={opt.key}
                      className={statusFilter === opt.key ? 'active' : ''}
                      onClick={() => { setStatusFilter(opt.key); setFilterOpen(false); }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button className="apx-tool-btn" onClick={exportCsv} disabled={filteredCatalog.length === 0}>
              <Download size={15} /> Export
            </button>
          </div>
        </div>

        <div className="apx-table">
          <div className="apx-thead">
            <span>Product</span>
            <span>SKU</span>
            <span>Vendor</span>
            <span className="apx-num">List price</span>
            <span className="apx-num">Managed/mo</span>
            <span>Status</span>
            <span />
          </div>

          {loading && <div className="apx-empty">Loading…</div>}
          {!loading && filteredCatalog.length === 0 && (
            <div className="apx-empty">No products match.</div>
          )}

          {filteredCatalog.map((item) => {
            const status = statusInfo(item);
            return (
              <div key={item.id} className="apx-row">
                <span className="apx-product">{item.name}</span>
                <span className="apx-sku">{item.sku}</span>
                <span className="apx-vendor">{item.vendor || '—'}</span>
                <span className="apx-num apx-price">{money(item.price)}</span>
                <span className="apx-num apx-managed">
                  {item.managed_service_price != null ? money(item.managed_service_price) : '—'}
                </span>
                <span>
                  <span className={`apx-status apx-status-${status.tone}`}>{status.label}</span>
                </span>
                <span className="apx-row-action">
                  {canManage && (
                    <button
                      className="apx-edit-btn"
                      title="Edit managed-service rate"
                      aria-label="Edit managed-service rate"
                      onClick={() => openRateEditor(item)}
                    >
                      <Pencil size={15} />
                    </button>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Managed-rate editor (row pencil) */}
      {rateItem && (
        <div className="apx-modal-overlay" onClick={() => setRateItem(null)}>
          <div className="apx-modal apx-modal-sm" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setRateItem(null)}><X size={18} /></button>
            <h3 className="apx-modal-title">Managed-service rate</h3>
            <p className="apx-modal-sub">{rateItem.name} · <span className="apx-sku">{rateItem.sku}</span></p>
            <label className="apx-field">
              <span>Managed / month (USD)</span>
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder="e.g. 89.00"
                value={rateValue}
                onChange={(e) => setRateValue(e.target.value)}
              />
            </label>
            <p className="mini-note">Leave blank to remove the managed-service rate for this device.</p>
            <div className="apx-modal-foot">
              <button className="apx-ghost-btn" onClick={() => setRateItem(null)}>Cancel</button>
              <button className="apx-add-btn" onClick={saveRate} disabled={savingRate}>
                <Save size={15} /> {savingRate ? 'Saving…' : 'Save rate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Product / component editor (existing CRUD, preserved in a modal) */}
      {editorOpen && (
        <div className="apx-modal-overlay" onClick={() => setEditorOpen(false)}>
          <div className="apx-modal apx-modal-lg" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setEditorOpen(false)}><X size={18} /></button>
            <h3 className="apx-modal-title">Manage products &amp; components</h3>
            <p className="apx-modal-sub">Create SKUs and edit the components that feed the live pricing engine.</p>

            {canManage && (
              <div className="selector-card" style={{ marginBottom: 14 }}>
                <h3>Add Product (SKU header)</h3>
                <div className="inline-fields">
                  <input placeholder="Vendor" value={newProduct.vendor} onChange={(e) => setNewProduct({ ...newProduct, vendor: e.target.value })} />
                  <input placeholder="Technology" value={newProduct.technology} onChange={(e) => setNewProduct({ ...newProduct, technology: e.target.value })} />
                </div>
                <div className="inline-fields">
                  <input placeholder="SKU" value={newProduct.sku} onChange={(e) => setNewProduct({ ...newProduct, sku: e.target.value })} />
                  <input placeholder="Name" value={newProduct.name} onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })} />
                </div>
                <div className="inline-fields">
                  <select value={newProduct.default_financial_model} onChange={(e) => setNewProduct({ ...newProduct, default_financial_model: e.target.value })}>
                    {FINANCIAL_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <input placeholder="Margin % (e.g. 0.20)" value={newProduct.margin_pct} onChange={(e) => setNewProduct({ ...newProduct, margin_pct: e.target.value })} />
                  <input placeholder="Leasing % (e.g. 0.05)" value={newProduct.leasing_pct} onChange={(e) => setNewProduct({ ...newProduct, leasing_pct: e.target.value })} />
                </div>
                <button className="primary-btn" onClick={onCreateProduct} disabled={!newProduct.vendor || !newProduct.technology || !newProduct.sku || !newProduct.name}>
                  <Plus size={14} /> Create Product
                </button>
              </div>
            )}

            <div className="table-wrap">
              <table className="cart-table">
                <thead>
                  <tr><th>Vendor</th><th>Technology</th><th>SKU</th><th>Name</th><th>Model</th><th>Margin</th><th>Leasing</th><th>Active</th></tr>
                </thead>
                <tbody>
                  {products.map((p) => (
                    <tr key={p.id} onClick={() => selectProduct(p.id)} style={{ cursor: 'pointer', background: selected?.id === p.id ? 'var(--surface-pressed)' : undefined }}>
                      <td>{p.vendor}</td>
                      <td>{p.technology}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}>{p.sku}</td>
                      <td>{p.name}</td>
                      <td>{p.default_financial_model}</td>
                      <td>{p.margin_pct ?? '—'}</td>
                      <td>{p.leasing_pct ?? '—'}</td>
                      <td>{p.is_active ? '✓' : '—'}</td>
                    </tr>
                  ))}
                  {products.length === 0 && <tr><td colSpan={8} style={{ color: 'var(--muted)' }}>No products yet.</td></tr>}
                </tbody>
              </table>
            </div>

            {selected && (
              <div className="dashboard-panel" style={{ marginTop: 18 }}>
                <h3>{selected.sku} — {selected.name}</h3>
                <p className="mini-note">{selected.vendor} · {selected.technology} · {selected.default_financial_model}</p>

                <div className="table-wrap" style={{ marginTop: 10 }}>
                  <table className="ams-table">
                    <thead>
                      <tr>
                        <th>Type</th><th>Label</th><th>Vendor SKU</th><th>Cost</th><th>MSRP</th><th>UoM</th>
                        <th>Billing</th><th>Interval</th><th>Margin</th><th>Req</th><th>Active</th><th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.components.map((c) => (
                        <tr key={c.id}>
                          <td style={{ fontSize: '0.78rem' }}>{c.component_type}</td>
                          <td><input value={c.label} onChange={(e) => patchComponentLocal(c.id, 'label', e.target.value)} /></td>
                          <td style={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>{c.vendor_component_sku || '—'}</td>
                          <td><input className="ams-price-input" type="number" step="0.0001" value={c.vendor_cost} onChange={(e) => patchComponentLocal(c.id, 'vendor_cost', Number(e.target.value))} /></td>
                          <td><input className="ams-price-input" type="number" step="0.01" value={c.msrp ?? ''} onChange={(e) => patchComponentLocal(c.id, 'msrp', e.target.value === '' ? null : Number(e.target.value))} /></td>
                          <td>
                            <select value={c.uom} onChange={(e) => patchComponentLocal(c.id, 'uom', e.target.value)}>
                              {UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
                            </select>
                          </td>
                          <td>
                            <select value={c.billing} onChange={(e) => patchComponentLocal(c.id, 'billing', e.target.value)}>
                              <option value="ONE_TIME">ONE_TIME</option>
                              <option value="RECURRING">RECURRING</option>
                            </select>
                          </td>
                          <td>
                            <select value={c.interval ?? ''} onChange={(e) => patchComponentLocal(c.id, 'interval', e.target.value || null)}>
                              <option value="">—</option>
                              <option value="MONTH">MONTH</option>
                              <option value="YEAR">YEAR</option>
                            </select>
                          </td>
                          <td><input className="ams-price-input" style={{ width: 70 }} type="number" step="0.0001" value={c.margin_pct ?? ''} onChange={(e) => patchComponentLocal(c.id, 'margin_pct', e.target.value === '' ? null : Number(e.target.value))} /></td>
                          <td><input type="checkbox" checked={c.is_required} onChange={(e) => patchComponentLocal(c.id, 'is_required', e.target.checked)} /></td>
                          <td><input type="checkbox" checked={c.is_active} onChange={(e) => patchComponentLocal(c.id, 'is_active', e.target.checked)} /></td>
                          <td>{canManage && <button className="secondary-btn" onClick={() => onSaveComponentRow(c)}><Save size={12} /></button>}</td>
                        </tr>
                      ))}
                      {selected.components.length === 0 && <tr><td colSpan={12} style={{ color: 'var(--muted)' }}>No components.</td></tr>}
                    </tbody>
                  </table>
                </div>

                {canManage && (
                  <div className="selector-card" style={{ marginTop: 12 }}>
                    <h3>Add Component</h3>
                    <div className="inline-fields">
                      <select value={newComponent.component_type} onChange={(e) => setNewComponent({ ...newComponent, component_type: e.target.value })}>
                        {COMPONENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                      <input placeholder="Label" value={newComponent.label} onChange={(e) => setNewComponent({ ...newComponent, label: e.target.value })} />
                    </div>
                    <div className="inline-fields">
                      <input placeholder="Vendor SKU" value={newComponent.vendor_component_sku} onChange={(e) => setNewComponent({ ...newComponent, vendor_component_sku: e.target.value })} />
                      <input placeholder="Vendor cost" type="number" step="0.0001" value={newComponent.vendor_cost} onChange={(e) => setNewComponent({ ...newComponent, vendor_cost: e.target.value })} />
                    </div>
                    <div className="inline-fields">
                      <select value={newComponent.uom} onChange={(e) => setNewComponent({ ...newComponent, uom: e.target.value })}>
                        {UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
                      </select>
                      <select value={newComponent.billing} onChange={(e) => setNewComponent({ ...newComponent, billing: e.target.value })}>
                        <option value="ONE_TIME">ONE_TIME</option>
                        <option value="RECURRING">RECURRING</option>
                      </select>
                      <select value={newComponent.interval} onChange={(e) => setNewComponent({ ...newComponent, interval: e.target.value })}>
                        <option value="">no interval</option>
                        <option value="MONTH">MONTH</option>
                        <option value="YEAR">YEAR</option>
                      </select>
                    </div>
                    <button className="primary-btn" onClick={onAddComponent} disabled={!newComponent.label || newComponent.vendor_cost === ''}>
                      <Plus size={14} /> Add Component
                    </button>
                  </div>
                )}

                <div className="selector-card" style={{ marginTop: 12 }}>
                  <h3><Calculator size={14} /> Live Price Preview</h3>
                  <div className="inline-fields">
                    <select value={previewModel} onChange={(e) => setPreviewModel(e.target.value)}>
                      <option value="CAPEX">CAPEX</option>
                      <option value="OPEX">OPEX</option>
                    </select>
                    <select value={previewInterval} onChange={(e) => setPreviewInterval(e.target.value)}>
                      <option value="MONTH">Monthly</option>
                      <option value="YEAR">Annual</option>
                    </select>
                  </div>
                  <p className="mini-note">Tick optional components to include them (required ones are always priced):</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '6px 0' }}>
                    {selected.components.filter((c) => !c.is_required && c.is_active).map((c) => (
                      <label key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                        <input type="checkbox" checked={(selections[c.id] ?? 0) > 0}
                          onChange={(e) => setSelections((s) => ({ ...s, [c.id]: e.target.checked ? 1 : 0 }))} />
                        {c.label}
                        {(selections[c.id] ?? 0) > 0 && (
                          <input type="number" min={1} style={{ width: 50 }} value={selections[c.id]}
                            onChange={(e) => setSelections((s) => ({ ...s, [c.id]: Number(e.target.value) }))} />
                        )}
                      </label>
                    ))}
                  </div>
                  <button className="secondary-btn" onClick={runPreview}><Calculator size={12} /> Compute</button>

                  {preview && (
                    <div style={{ marginTop: 10 }}>
                      <table className="ams-table">
                        <thead><tr><th>Component</th><th>Qty</th><th>Billing</th><th>Unit</th><th>Line</th></tr></thead>
                        <tbody>
                          {preview.lines.map((l) => (
                            <tr key={l.component_id}>
                              <td>{l.label}{l.financed ? ' (financed)' : ''}</td>
                              <td>{l.qty}</td>
                              <td>{l.billing}{l.interval ? `/${l.interval}` : ''}</td>
                              <td>${l.unit_price.toFixed(2)}</td>
                              <td>${l.line_total.toFixed(2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <div className="ams-actions" style={{ gap: 18 }}>
                        <span><strong>One-time:</strong> ${preview.one_time_total.toFixed(2)}</span>
                        <span><strong>Recurring ({preview.interval === 'YEAR' ? 'yr' : 'mo'}):</strong> ${preview.recurring_total_at_interval.toFixed(2)}</span>
                        <span><strong>Projected {preview.term_months}-mo:</strong> ${preview.projected_term_cost.toFixed(2)}</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
};
