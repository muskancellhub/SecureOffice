import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, Building2, Camera, Laptop, Network, Pencil, Plus, Radio,
  RadioTower, Router, Save, Search, ShieldCheck, Smartphone, Tablet, Wifi, X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import * as tenantSettingsApi from '../api/tenantSettingsApi';
import { useAuth } from '../context/AuthContext';
import { useTenant } from '../context/TenantContext';
import type { CatalogItem } from '../types/commerce';
import type { TenantSettings } from '../types/tenantSettings';
import { extractApiError } from '../utils/extractApiError';

// Category groups whose availability a tenant can toggle (per-tenant enablement).
const CATEGORY_GROUPS = [
  { key: 'network', label: 'Network', categories: ['router', 'wifi_ap', 'switch', 'firewall', 'cellular_gateway'] },
  { key: 'security', label: 'Security', categories: ['security_appliance', 'camera', 'sensor'] },
  { key: 'end_user_devices', label: 'End User Devices', categories: ['laptop', 'phone', 'tablet', 'hotspot'] },
];

const CATEGORY_ICON: Record<string, LucideIcon> = {
  router: Router, wifi_ap: Wifi, switch: Network, firewall: ShieldCheck, cellular_gateway: RadioTower,
  security_appliance: ShieldCheck, camera: Camera, sensor: Radio,
  laptop: Laptop, phone: Smartphone, tablet: Tablet, hotspot: Wifi,
};

const FALLBACK_ICON: LucideIcon = Activity;

const groupKeyForCategory = (category: string): string | null =>
  CATEGORY_GROUPS.find((g) => g.categories.includes(category))?.key ?? null;

const prettyCategory = (category?: string): string => {
  if (!category) return 'Service';
  return category
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
    .replace(/\bWifi\b/, 'Wi-Fi')
    .replace(/\bAp\b/, 'AP');
};

const formatPrice = (value: number): string =>
  '$' + new Intl.NumberFormat('en-US', {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value || 0);

export const AdminManagedServicesPage = () => {
  const { accessToken, user } = useAuth();
  const { activeTenant, activeTenantId } = useTenant();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';

  const [devices, setDevices] = useState<CatalogItem[]>([]);
  const [settings, setSettings] = useState<TenantSettings | null>(null);
  const [orgName, setOrgName] = useState('');
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  // edit modal
  const [rateItem, setRateItem] = useState<CatalogItem | null>(null);
  const [rateValue, setRateValue] = useState('');
  const [savingRate, setSavingRate] = useState(false);

  // new-service modal
  const [newOpen, setNewOpen] = useState(false);
  const [newDeviceId, setNewDeviceId] = useState('');
  const [newPrice, setNewPrice] = useState('');

  const load = useCallback(async () => {
    if (!accessToken || !isAdmin) return;
    setLoading(true);
    try {
      const [data, profile] = await Promise.all([
        commerceApi.getCatalog(accessToken, { type: 'DEVICE', sort: 'recommended', page_size: 250 }),
        commerceApi.getOnboardingProfile(accessToken).catch(() => null),
      ]);
      setDevices(data);
      setOrgName(profile?.organization_name || '');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load devices'));
    } finally {
      setLoading(false);
    }
  }, [accessToken, isAdmin]);

  useEffect(() => { load(); }, [load]);

  const loadSettings = useCallback(async () => {
    if (!accessToken || !isAdmin) return;
    try {
      setSettings(await tenantSettingsApi.getTenantSettings(accessToken));
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load tenant settings'));
    }
  }, [accessToken, isAdmin, activeTenantId]);

  useEffect(() => { loadSettings(); }, [loadSettings]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(''), 2500);
    return () => window.clearTimeout(t);
  }, [notice]);

  const isCategoryEnabled = (key: string) =>
    settings?.admin_services?.enabled_categories?.[key] !== false;

  const toggleCategory = async (key: string) => {
    if (!accessToken) return;
    const base: TenantSettings = settings ?? {
      tenant_id: activeTenantId ?? '',
      design_ops: { sla_default_days: 5, auto_assign: false },
      admin_services: { enabled_categories: {} },
      feature_flags: {},
      updated_at: null,
    };
    const enabled = base.admin_services?.enabled_categories ?? {};
    const next: TenantSettings = {
      ...base,
      admin_services: { enabled_categories: { ...enabled, [key]: enabled[key] === false } },
    };
    setSettings(next);
    try {
      const updated = await tenantSettingsApi.updateTenantSettings(accessToken, { admin_services: next.admin_services });
      setSettings(updated);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to save category availability'));
    }
  };

  const services = useMemo(() => {
    const s = search.trim().toLowerCase();
    return devices.filter((d) => {
      if (!s) return true;
      const cat = d.attributes?.category || '';
      return [d.name, d.sku, cat].some((v) => (v || '').toLowerCase().includes(s));
    });
  }, [devices, search]);

  const configuredCount = useMemo(
    () => devices.filter((d) => d.managed_service_price != null).length,
    [devices],
  );

  const unpriced = useMemo(
    () => devices.filter((d) => d.managed_service_price == null),
    [devices],
  );

  const applyPrice = async (item: CatalogItem, value: number | null) => {
    if (!accessToken) return;
    setBusyId(item.id);
    setError('');
    try {
      const updated = await commerceApi.updateDeviceManagedServicePrice(accessToken, item.id, value);
      setDevices((rows) => rows.map((r) => (r.id === item.id ? { ...r, managed_service_price: updated.managed_service_price } : r)));
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to update managed-service rate'));
      throw err;
    } finally {
      setBusyId(null);
    }
  };

  const toggleEnabled = async (item: CatalogItem) => {
    if (item.managed_service_price != null) {
      // disable → clear the rate
      await applyPrice(item, null).catch(() => {});
    } else {
      // enable → must set a rate, open the editor
      setRateItem(item);
      setRateValue('');
    }
  };

  const openEditor = (item: CatalogItem) => {
    setRateItem(item);
    setRateValue(item.managed_service_price != null ? String(item.managed_service_price) : '');
  };

  const saveRate = async () => {
    if (!rateItem) return;
    setSavingRate(true);
    try {
      const value = rateValue.trim() === '' ? null : Number(rateValue);
      await applyPrice(rateItem, value);
      setNotice(`Saved ${rateItem.name}`);
      setRateItem(null);
    } catch { /* error surfaced in applyPrice */ } finally {
      setSavingRate(false);
    }
  };

  const createService = async () => {
    const device = devices.find((d) => d.id === newDeviceId);
    if (!device) return;
    try {
      await applyPrice(device, newPrice.trim() === '' ? 0 : Number(newPrice));
      setNotice(`Enabled managed service for ${device.name}`);
      setNewOpen(false);
      setNewDeviceId('');
      setNewPrice('');
    } catch { /* surfaced */ }
  };

  if (!isAdmin) {
    return <section className="content-wrap fade-in"><div className="error-text">Admin access required.</div></section>;
  }

  return (
    <section className="content-wrap fade-in admin-managed-page">
      <header className="apx-header">
        <div className="apx-header-text">
          <span className="apx-eyebrow"><ShieldCheck size={15} /> Admin</span>
          <h1>Managed services</h1>
          <p className="apx-subtitle">Configure service catalog, pricing, and category enablement.</p>
          <div className="apx-scope">
            <span className="apx-scope-chip"><Building2 size={14} /> Scope: {orgName || activeTenant?.name || 'All tenants'}</span>
            <span className="apx-scope-meta">{configuredCount} services · {devices.length} devices</span>
          </div>
        </div>
        <button className="apx-add-btn" onClick={() => setNewOpen(true)} disabled={unpriced.length === 0}>
          <Plus size={18} /> New service
        </button>
      </header>

      {error && <div className="error-text">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}

      <div className="amx-catbar">
        <span className="amx-catbar-label">Category enablement</span>
        {CATEGORY_GROUPS.map((g) => {
          const on = isCategoryEnabled(g.key);
          return (
            <button
              key={g.key}
              className={`amx-cat-chip ${on ? 'on' : ''}`}
              onClick={() => toggleCategory(g.key)}
              title={`${on ? 'Disable' : 'Enable'} ${g.label} for ${activeTenant?.name ?? 'this tenant'}`}
            >
              <span className="amx-cat-dot" /> {g.label}
            </button>
          );
        })}
      </div>

      <div className="amx-table-card">
        <div className="amx-table-toolbar">
          <div className="apx-search">
            <Search size={16} />
            <input placeholder="Search services & SKUs…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>

        <div className="amx-table">
          <div className="amx-thead">
            <span>Service</span>
            <span>Category</span>
            <span className="amx-num">Price</span>
            <span>Unit</span>
            <span className="amx-center">Enabled</span>
            <span />
          </div>

          {loading && <div className="apx-empty">Loading…</div>}
          {!loading && services.length === 0 && <div className="apx-empty">No services match.</div>}

          {services.map((item) => {
            const category = item.attributes?.category || '';
            const Icon = CATEGORY_ICON[category] || FALLBACK_ICON;
            const enabled = item.managed_service_price != null;
            const isBusy = busyId === item.id;
            return (
              <div key={item.id} className="amx-row">
                <span className="amx-service">
                  <span className="amx-svc-icon"><Icon size={18} /></span>
                  <span className="amx-svc-name">{item.name}</span>
                </span>
                <span><span className="amx-cat-tag">{prettyCategory(category)}</span></span>
                <span className="amx-num amx-price">{enabled ? formatPrice(item.managed_service_price as number) : '—'}</span>
                <span className="amx-unit">per device / mo</span>
                <span className="amx-center">
                  <button
                    className={`amx-toggle ${enabled ? 'on' : ''}`}
                    role="switch"
                    aria-checked={enabled}
                    aria-label={enabled ? 'Disable managed service' : 'Enable managed service'}
                    disabled={isBusy}
                    onClick={() => toggleEnabled(item)}
                  />
                </span>
                <span className="amx-row-action">
                  <button className="apx-edit-btn" title="Edit price" aria-label="Edit price" onClick={() => openEditor(item)}>
                    <Pencil size={15} />
                  </button>
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Edit / set managed-service rate */}
      {rateItem && (
        <div className="apx-modal-overlay" onClick={() => setRateItem(null)}>
          <div className="apx-modal apx-modal-sm" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setRateItem(null)}><X size={18} /></button>
            <h3 className="apx-modal-title">Managed-service rate</h3>
            <p className="apx-modal-sub">{rateItem.name} · <span className="apx-sku">{rateItem.sku}</span></p>
            <label className="apx-field">
              <span>Price per device / month (USD)</span>
              <input type="number" step="0.01" min="0" placeholder="e.g. 89.00" value={rateValue} onChange={(e) => setRateValue(e.target.value)} autoFocus />
            </label>
            <p className="mini-note">Leave blank to disable the managed service for this SKU.</p>
            <div className="apx-modal-foot">
              <button className="apx-ghost-btn" onClick={() => setRateItem(null)}>Cancel</button>
              <button className="apx-add-btn" onClick={saveRate} disabled={savingRate}>
                <Save size={15} /> {savingRate ? 'Saving…' : 'Save rate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New service (assign a managed rate to a device that has none) */}
      {newOpen && (
        <div className="apx-modal-overlay" onClick={() => setNewOpen(false)}>
          <div className="apx-modal apx-modal-sm" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setNewOpen(false)}><X size={18} /></button>
            <h3 className="apx-modal-title">New managed service</h3>
            <p className="apx-modal-sub">Assign a managed-service rate to a device SKU.</p>
            <label className="apx-field">
              <span>Device SKU</span>
              <select value={newDeviceId} onChange={(e) => setNewDeviceId(e.target.value)}>
                <option value="">Select a device…</option>
                {unpriced.map((d) => (
                  <option key={d.id} value={d.id}>{d.name} ({d.sku})</option>
                ))}
              </select>
            </label>
            <label className="apx-field">
              <span>Price per device / month (USD)</span>
              <input type="number" step="0.01" min="0" placeholder="e.g. 89.00" value={newPrice} onChange={(e) => setNewPrice(e.target.value)} />
            </label>
            <div className="apx-modal-foot">
              <button className="apx-ghost-btn" onClick={() => setNewOpen(false)}>Cancel</button>
              <button className="apx-add-btn" onClick={createService} disabled={!newDeviceId}>
                <Plus size={15} /> Add service
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
