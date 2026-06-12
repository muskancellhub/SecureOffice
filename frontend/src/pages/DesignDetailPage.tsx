import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowUpRight,
  DollarSign,
  Layers,
  MapPin,
  Network,
  Server,
  ShoppingCart,
  Trash2,
  Wifi,
} from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import { DrawioDiagramViewer } from '../components/DrawioDiagramViewer';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import { extractApiError } from '../utils/extractApiError';
import type {
  DesignInstallAssistance,
  ManagedServicesDesignSummary,
  ManagedServiceDeviceEntry,
  NetworkBomLine,
  NetworkDesignDetail,
} from '../types/commerce';

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value || 0);

const isQuoteRequiredLine = (line: NetworkBomLine): boolean => {
  const unit = Number(line.unit_price || 0);
  if (unit > 0) return false;
  const source = String(line.source_type || '').toLowerCase();
  return source === 'paapi' || source === 'derived';
};

const formatBomMoney = (line: NetworkBomLine, kind: 'unit' | 'total'): string => {
  const value = kind === 'unit' ? Number(line.unit_price || 0) : Number(line.line_total || 0);
  if (value <= 0 && isQuoteRequiredLine(line)) return 'Price on request';
  return formatCurrency(value);
};

const connectivityLabel = (value: NetworkBomLine['connectivity'] | undefined): string | null => {
  if (value === 'wired') return 'Wired link';
  if (value === 'wireless') return 'Wireless link';
  if (value === 'sim') return 'SIM / 5G link';
  return null;
};

const formatDate = (value?: string | null): string => {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
};

const defaultInstallState: DesignInstallAssistance = {
  installMode: 'self_install',
  preferredInstallDate: '',
  installNotes: '',
};

export const DesignDetailPage = () => {
  const { accessToken } = useAuth();
  const { refreshCart } = useShop();
  const navigate = useNavigate();
  const { designId } = useParams();
  const [design, setDesign] = useState<NetworkDesignDetail | null>(null);
  const [installAssistance, setInstallAssistance] = useState<DesignInstallAssistance>(defaultInstallState);
  const [loading, setLoading] = useState(false);
  const [savingInstall, setSavingInstall] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [msData, setMsData] = useState<ManagedServicesDesignSummary | null>(null);
  const [msSaving, setMsSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [addingAllToCart, setAddingAllToCart] = useState(false);

  const loadDesign = async () => {
    if (!accessToken || !designId) return;
    setLoading(true);
    setError('');
    try {
      const data = await commerceApi.getNetworkDesign(accessToken, designId);
      setDesign(data);
      // Always fetch managed services via dedicated endpoint for freshest data
      loadManagedServices(data.id);
      setInstallAssistance({
        installMode: data.installAssistance?.installMode || 'self_install',
        preferredInstallDate: data.installAssistance?.preferredInstallDate || '',
        installNotes: data.installAssistance?.installNotes || '',
      });
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load design details'));
    } finally {
      setLoading(false);
    }
  };

  const loadManagedServices = useCallback(async (id?: string) => {
    const did = id || designId;
    if (!accessToken || !did) return;
    try {
      const data = await commerceApi.getDesignManagedServices(accessToken, did);
      setMsData(data);
    } catch (err) {
      console.warn('[ManagedServices] Failed to load:', err);
    }
  }, [accessToken, designId]);

  useEffect(() => {
    loadDesign();
  }, [accessToken, designId]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 2600);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const bomLines = useMemo(() => {
    const lines = (design?.bom as { line_items?: NetworkBomLine[] })?.line_items;
    return Array.isArray(lines) ? lines : [];
  }, [design?.bom]);

  const quoteRequiredCount = useMemo(
    () => bomLines.filter((line) => isQuoteRequiredLine(line)).length,
    [bomLines],
  );

  const orderableLines = useMemo(() => bomLines.filter((line) => Boolean(line.item_id)), [bomLines]);

  const onAddAllToCart = async () => {
    if (!accessToken) return;
    if (orderableLines.length === 0) { setNotice('No catalog-linked BOM items to add.'); return; }
    setAddingAllToCart(true);
    setError('');
    let ok = 0;
    let fail = 0;
    for (const line of orderableLines) {
      try {
        await commerceApi.addCartLine(accessToken, { product_id: line.item_id as string, quantity: Math.max(1, line.quantity) });
        ok += 1;
      } catch {
        fail += 1;
      }
    }
    if (ok > 0) await refreshCart();
    setAddingAllToCart(false);
    if (ok > 0) {
      setNotice(`Added ${ok} BOM item${ok > 1 ? 's' : ''} to cart.`);
      setTimeout(() => navigate('/shop/cart'), 600);
    }
    if (fail > 0) setError(`${fail} item${fail > 1 ? 's' : ''} could not be added to cart.`);
  };


  // Build per-item lookup from managed services data
  // Handle both camelCase (from dedicated API) and snake_case (from inline detail)
  const msDeviceMap = useMemo(() => {
    const map = new Map<string, ManagedServiceDeviceEntry & { group: string; groupEnabled: boolean }>();
    if (!msData?.categories) return map;
    for (const cat of msData.categories) {
      for (const raw of (cat.devices || []) as any[]) {
        const device: ManagedServiceDeviceEntry = {
          itemId: raw.itemId || raw.item_id,
          name: raw.name,
          sku: raw.sku,
          category: raw.category,
          quantity: raw.quantity,
          managedServicePrice: raw.managedServicePrice ?? raw.managed_service_price ?? 0,
          excluded: raw.excluded ?? false,
        };
        if (device.itemId) {
          map.set(device.itemId, { ...device, group: cat.group, groupEnabled: cat.enabled !== false });
        }
      }
    }
    return map;
  }, [msData]);

  const msTotalMonthly = msData?.grandTotalMonthly ?? 0;

  // Toggle managed-service coverage for a SINGLE device. `currentlyIncluded` is
  // the checkbox's visible checked state (group enabled AND not excluded) — we
  // key off that, not the raw `excluded` flag, because while a group is disabled
  // every device reads `excluded:false` yet shows unchecked.
  const toggleMsForDevice = async (itemId: string, currentlyIncluded: boolean) => {
    if (!accessToken || !designId || !msData) return;
    const config = msData.config || {};
    const rawEnabled = (config as any).enabled_categories || (config as any).enabledCategories || [];
    const excludedSet = new Set<string>((config as any).excluded_item_ids || (config as any).excludedItemIds || []);

    // The backend treats an EMPTY enabled list as "all categories enabled". Mirror
    // that here so our notion of "enabled" matches the server's — otherwise, on a
    // default (all-on) design, re-checking a device would wrongly look like it's
    // enabling a fresh category and exclude its siblings.
    const allGroups = msData.categories.map((c) => c.group);
    const enabledSet = new Set<string>(rawEnabled.length > 0 ? rawEnabled : allGroups);

    const deviceInfo = msDeviceMap.get(itemId);
    const group = deviceInfo?.group;

    if (currentlyIncluded) {
      // Turn this device OFF — exclude it, leaving the category enabled for others.
      excludedSet.add(itemId);
    } else {
      // Turn this device ON. If its category isn't enabled yet, enabling it would
      // otherwise auto-include every sibling (they default to excluded:false), so
      // exclude all the other devices in the group first — only this one turns on.
      if (group && !enabledSet.has(group)) {
        enabledSet.add(group);
        for (const [otherId, info] of msDeviceMap) {
          if (info.group === group && otherId !== itemId) excludedSet.add(otherId);
        }
      }
      excludedSet.delete(itemId);
    }

    // Optimistic update — derive each device's excluded + each category's enabled
    // straight from the recomputed sets so the whole table stays consistent.
    setMsData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        categories: prev.categories.map((cat) => {
          const enabled = enabledSet.has(cat.group);
          const devices = cat.devices.map((d) => ({ ...d, excluded: excludedSet.has(d.itemId) }));
          const isOn = (d: typeof devices[number]) => enabled && !excludedSet.has(d.itemId);
          return {
            ...cat,
            enabled,
            devices,
            appliedCount: devices.reduce((sum, d) => sum + (isOn(d) ? d.quantity : 0), 0),
            excludedCount: devices.reduce((sum, d) => sum + (isOn(d) ? 0 : d.quantity), 0),
            monthlyTotal: devices.reduce((sum, d) => sum + (isOn(d) ? d.managedServicePrice * d.quantity : 0), 0),
          };
        }),
      };
    });

    // Sync with backend in the background (no msSaving spinner to avoid blink)
    try {
      const result = await commerceApi.updateDesignManagedServices(accessToken, designId, {
        enabledCategories: [...enabledSet],
        excludedItemIds: [...excludedSet],
      });
      // Reconcile server truth for the grand total
      setMsData(result);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to update managed service'));
      // Revert on error
      loadManagedServices();
    }
  };

  const onDeleteDesign = async () => {
    if (!accessToken || !design) return;
    const name = design.designName || `Design ${design.id.slice(0, 8)}`;
    const confirmed = window.confirm(`Delete "${name}"? This cannot be undone.`);
    if (!confirmed) return;
    setDeleting(true);
    setError('');
    try {
      await commerceApi.deleteNetworkDesign(accessToken, design.id);
      navigate('/shop/designs');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to delete design'));
      setDeleting(false);
    }
  };

  const onSaveInstallAssistance = async () => {
    if (!accessToken || !design) return;
    setSavingInstall(true);
    setError('');
    try {
      const updated = await commerceApi.updateNetworkDesignInstallAssistance(accessToken, design.id, {
        installMode: installAssistance.installMode || undefined,
        preferredInstallDate: installAssistance.preferredInstallDate || undefined,
        installNotes: installAssistance.installNotes || undefined,
      });
      setDesign(updated);
      setNotice('Installation preference saved.');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to save installation preference'));
    } finally {
      setSavingInstall(false);
    }
  };

  const designLabel = design ? (design.designName || `Design ${design.id.slice(0, 8)}`) : '';
  const canDelete = !!design;

  return (
    <section className="content-wrap fade-in dnb-page design-detail-page">
      {loading && !design && <div className="dd-loading">Loading design…</div>}
      {error && <div className="onboarding-alert error">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}

      {design && (
        <>
          {/* ── Header ──────────────────────────────────────────────── */}
          <header className="apx-header">
            <div className="apx-header-text">
              <Link to="/shop/designs" className="dnb-back"><ArrowLeft size={15} /> Back to designs</Link>
              <h1>{designLabel}</h1>
              <p className="apx-subtitle">Saved network design — bill of materials and topology.</p>
              <div className="apx-scope">
                <span className="apx-scope-meta">Updated {formatDate(design.statusUpdatedAt || design.updatedAt)}</span>
                {design.quoteId && (
                  <button type="button" className="dnb-meta-link" onClick={() => navigate(`/shop/quotes/${design.quoteId}`)}>
                    Quote {design.quoteId.slice(0, 8).toUpperCase()} <ArrowUpRight size={13} />
                  </button>
                )}
                {design.orderId && (
                  <button type="button" className="dnb-meta-link" onClick={() => navigate(`/shop/orders/${design.orderId}`)}>
                    Order {design.orderId.slice(0, 8).toUpperCase()} <ArrowUpRight size={13} />
                  </button>
                )}
              </div>
            </div>
            <button
              className="apx-add-btn dnb-order-btn"
              onClick={onAddAllToCart}
              disabled={addingAllToCart || orderableLines.length === 0}
            >
              <ShoppingCart size={18} /> {addingAllToCart ? 'Adding…' : 'Order this design'}
            </button>
          </header>

          {/* ── Lifecycle toolbar ───────────────────────────────────── */}
          <div className="dnb-toolbar">
            {design.quoteId && (
              <button className="dnb-tool-btn" onClick={() => navigate(`/shop/quotes/${design.quoteId}`)}>
                <ArrowUpRight size={15} /> Open quote
              </button>
            )}
            {design.orderId && (
              <button className="dnb-tool-btn" onClick={() => navigate(`/shop/orders/${design.orderId}`)}>
                <ArrowUpRight size={15} /> View order
              </button>
            )}
          </div>

          {/* ── Stats ───────────────────────────────────────────────── */}
          <div className="apx-stats dnb-stats">
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Estimated CapEx</span><span className="apx-stat-icon green"><DollarSign size={16} /></span></div>
              <div className="apx-stat-value">{formatCurrency(design.estimatedCapex)}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Access points</span><span className="apx-stat-icon blue"><Wifi size={16} /></span></div>
              <div className="apx-stat-value">{design.apCount}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Switches</span><span className="apx-stat-icon violet"><Network size={16} /></span></div>
              <div className="apx-stat-value">{design.switchCount}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>{msTotalMonthly > 0 ? 'Managed / mo' : 'BOM lines'}</span><span className="apx-stat-icon amber">{msTotalMonthly > 0 ? <Server size={16} /> : <Layers size={16} />}</span></div>
              <div className="apx-stat-value">{msTotalMonthly > 0 ? formatCurrency(msTotalMonthly) : bomLines.length}</div>
            </article>
          </div>

          {/* ── Diagram — shown first, the main artifact ────────────── */}
          <div className="apx-table-card dnb-diagram-card" id="dd-diagram">
            <div className="dnb-card-head">
              <h3 className="apx-modal-title" style={{ margin: 0 }}>Network diagram</h3>
              <div className="dnb-diagram-meta">
                <span>{(design.topology?.nodes || []).length} nodes</span>
                <span>{(design.topology?.edges || []).length} edges</span>
              </div>
            </div>
            {design.drawioXml ? (
              <DrawioDiagramViewer
                xml={design.drawioXml}
                title={`${design.designName || 'Network Design'} Diagram`}
                initialHeight={640}
              />
            ) : (
              <div className="dnb-diagram-empty">
                <Network size={30} strokeWidth={1.3} />
                <p>No diagram has been generated yet.</p>
              </div>
            )}
          </div>

          {/* ── Bill of materials ───────────────────────────────────── */}
          <div className="apx-table-card dnb-bom-card" id="dd-bom">
            <div className="dnb-card-head">
              <h3 className="apx-modal-title" style={{ margin: 0 }}>Bill of materials</h3>
              {quoteRequiredCount > 0 && <span className="dnb-quote-note">{quoteRequiredCount} price-on-request</span>}
            </div>
            {bomLines.length > 0 ? (
              <table className="dnb-bom">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Category</th>
                    <th className="dnb-num">Qty</th>
                    <th className="dnb-num">Unit</th>
                    <th className="dnb-num">Total</th>
                    <th className="dnb-num">Managed / mo</th>
                  </tr>
                </thead>
                <tbody>
                  {bomLines.map((line) => {
                    const msDevice = line.item_id ? msDeviceMap.get(line.item_id) : undefined;
                    const hasMsPrice = msDevice && msDevice.managedServicePrice > 0;
                    const msIncluded = hasMsPrice && msDevice.groupEnabled && !msDevice.excluded;
                    return (
                      <tr key={line.line_id}>
                        <td>
                          <div className="dnb-bom-name">{line.name}</div>
                          {(line.connectivity || line.cable_type) && (
                            <div className="dnb-bom-sub">
                              {line.cable_type && line.cable_length_meters
                                ? `${line.cable_type} • ${Math.round(line.cable_length_meters)}m • $${Number(line.price_per_meter || 0).toFixed(2)}/m`
                                : connectivityLabel(line.connectivity)}
                            </div>
                          )}
                        </td>
                        <td><span className="dnb-cat-tag">{line.category || '—'}</span></td>
                        <td className="dnb-num">{line.quantity}</td>
                        <td className="dnb-num">{formatBomMoney(line, 'unit')}</td>
                        <td className="dnb-num dnb-total">{formatBomMoney(line, 'total')}</td>
                        <td className="dnb-num">
                          {hasMsPrice ? (
                            <label className="ms-inline-check">
                              <input
                                type="checkbox"
                                checked={msIncluded}
                                onChange={() => toggleMsForDevice(msDevice.itemId, !!msIncluded)}
                              />
                              <span className={msIncluded ? 'ms-inline-price' : 'ms-inline-price ms-inline-excluded'}>
                                ${msDevice.managedServicePrice.toFixed(2)}
                              </span>
                            </label>
                          ) : (
                            <span className="dnb-dash">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                {msTotalMonthly > 0 && (
                  <tfoot>
                    <tr className="dnb-bom-foot">
                      <td colSpan={5} className="dnb-num">Total managed services</td>
                      <td className="dnb-num dnb-total">{formatCurrency(msTotalMonthly)}/mo</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            ) : (
              <p className="mini-note">No BOM lines yet.</p>
            )}
          </div>

          {/* ── Installation ────────────────────────────────────────── */}
          <section className="dd-section" id="dd-installation">
            <div className="dd-section-head">
              <h2><MapPin size={16} /> Installation Preference</h2>
              <span className="dd-section-sub">Choose how you'd like the equipment deployed</span>
            </div>
            <div className="dd-section-card">
              <p className="dd-card-help">
                We'll confirm scheduling once the order is approved.
              </p>
              <div className="dd-form-grid">
                <label>
                  <span>Install Mode</span>
                  <select
                    value={installAssistance.installMode || 'self_install'}
                    onChange={(e) =>
                      setInstallAssistance((prev) => ({ ...prev, installMode: e.target.value as DesignInstallAssistance['installMode'] }))
                    }
                  >
                    <option value="self_install">Self-install — we ship, you deploy</option>
                    <option value="remote_assistance">Remote / video assistance</option>
                    <option value="onsite_visit">Onsite technician visit</option>
                  </select>
                </label>
                <label>
                  <span>Preferred Install Date</span>
                  <input
                    type="date"
                    value={installAssistance.preferredInstallDate || ''}
                    onChange={(e) => setInstallAssistance((prev) => ({ ...prev, preferredInstallDate: e.target.value }))}
                  />
                </label>
                <label className="dd-form-full">
                  <span>Install Notes</span>
                  <textarea
                    rows={3}
                    value={installAssistance.installNotes || ''}
                    onChange={(e) => setInstallAssistance((prev) => ({ ...prev, installNotes: e.target.value }))}
                    placeholder="Site access, contact, building hours, etc."
                  />
                </label>
              </div>
              <div className="dd-form-actions">
                <button className="secondary-btn" onClick={onSaveInstallAssistance} disabled={savingInstall}>
                  {savingInstall ? 'Saving…' : 'Save Preference'}
                </button>
              </div>
            </div>
          </section>

          {/* ── Danger zone ─────────────────────────────────────────── */}
          {canDelete && (
            <section className="dd-section">
              <div className="dd-danger-zone">
                <div>
                  <h3><Trash2 size={14} /> Delete this design</h3>
                  <p>
                    Permanently remove this design and its bill of materials. This cannot be undone.
                    Available only while the design is in <strong>Draft</strong> or <strong>Reviewed</strong>.
                  </p>
                </div>
                <button
                  type="button"
                  className="dd-danger-btn"
                  onClick={onDeleteDesign}
                  disabled={deleting}
                >
                  <Trash2 size={14} /> {deleting ? 'Deleting…' : 'Delete Design'}
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </section>
  );
};
