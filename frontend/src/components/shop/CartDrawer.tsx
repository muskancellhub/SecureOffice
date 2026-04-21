import { ChevronDown, Heart, Minus, PanelRight, Plus, Shield, ShoppingCart, Sparkles, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as commerceApi from '../../api/commerceApi';
import { useAuth } from '../../context/AuthContext';
import { useShop } from '../../context/ShopContext';
import type { CartLine, CatalogItem } from '../../types/commerce';
import { getRouterImage } from '../../utils/productImages';

interface CartDrawerProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

type TabKey = 'items' | 'services' | 'notes';

const BUNDLE_GOAL = 12;
const BUNDLE_DISCOUNT_RATE = 0.1;

const GROUP_ORDER = ['PHONES', 'ROUTERS & GATEWAYS', 'CONNECTIVITY', 'ACCESSORIES'] as const;

const resolveGroup = (category: string | null | undefined): (typeof GROUP_ORDER)[number] => {
  const cat = (category || '').toLowerCase();
  if (cat.includes('phone')) return 'PHONES';
  if (cat.includes('router') || cat.includes('gateway')) return 'ROUTERS & GATEWAYS';
  if (cat.includes('sim') || cat.includes('line') || cat.includes('connect')) return 'CONNECTIVITY';
  return 'ACCESSORIES';
};

const singularLabel = (group: string): string => {
  switch (group) {
    case 'PHONES': return 'phone';
    case 'ROUTERS & GATEWAYS': return 'device';
    case 'CONNECTIVITY': return 'line';
    default: return 'device';
  }
};

const servicesForCategory = (services: CatalogItem[], category: string | null | undefined): CatalogItem[] => {
  if (!services || services.length === 0) return [];
  if (!category) return services;
  const normalized = category.toLowerCase();
  return services.filter((svc) => {
    const allowed = (svc.attributes?.applies_to_categories || []) as string[];
    if (!Array.isArray(allowed) || allowed.length === 0) return true;
    return allowed.map((c) => c.toLowerCase()).includes(normalized);
  });
};

export const CartDrawer = ({ collapsed = false, onToggleCollapse }: CartDrawerProps) => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const {
    cart,
    managedServices,
    loadingCart,
    cartError,
    attachManagedService,
    changeServiceTier,
    updateLineQuantity,
    removeLine,
  } = useShop();

  const [activeTab, setActiveTab] = useState<TabKey>('items');
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [expandedServicePicker, setExpandedServicePicker] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const [generatingQuote, setGeneratingQuote] = useState(false);

  const deviceLines = useMemo(
    () => (cart?.lines || []).filter((line) => line.item_type === 'DEVICE'),
    [cart],
  );

  const serviceLinesByRouter = useMemo(() => {
    const map = new Map<string, CartLine[]>();
    (cart?.lines || []).forEach((line) => {
      if (line.item_type === 'SERVICE' && line.applies_to_line_id) {
        if (!map.has(line.applies_to_line_id)) map.set(line.applies_to_line_id, []);
        map.get(line.applies_to_line_id)!.push(line);
      }
    });
    return map;
  }, [cart?.lines]);

  const standaloneServiceLines = useMemo(
    () => (cart?.lines || []).filter((line) => line.item_type === 'SERVICE' && !line.applies_to_line_id),
    [cart?.lines],
  );

  const groupedDevices = useMemo(() => {
    const map = new Map<string, CartLine[]>();
    deviceLines.forEach((line) => {
      const group = resolveGroup(line.category);
      if (!map.has(group)) map.set(group, []);
      map.get(group)!.push(line);
    });
    return GROUP_ORDER
      .map((g) => ({ name: g, lines: map.get(g) || [] }))
      .filter((g) => g.lines.length > 0);
  }, [deviceLines]);

  const totalDeviceUnits = useMemo(
    () => deviceLines.reduce((sum, line) => sum + line.quantity, 0),
    [deviceLines],
  );

  const devicesSubtotal = cart?.one_time_subtotal || 0;
  const recurringMonthly = cart?.monthly_subtotal || 0;
  const remainingToBundle = Math.max(0, BUNDLE_GOAL - totalDeviceUnits);
  const bundleEligible = totalDeviceUnits >= BUNDLE_GOAL;
  const bundleDiscountAmount = bundleEligible ? devicesSubtotal * BUNDLE_DISCOUNT_RATE : 0;
  const totalToday = Math.max(0, devicesSubtotal - bundleDiscountAmount);
  const bundleProgressPct = Math.min(100, Math.round((totalDeviceUnits / BUNDLE_GOAL) * 100));
  const draftNumber = useMemo(() => {
    const raw = cart?.id || '';
    const tail = raw.replace(/[^0-9a-zA-Z]/g, '').slice(-4).toUpperCase() || '0000';
    return `A-${tail}`;
  }, [cart?.id]);

  const onGenerateQuote = async () => {
    if (!accessToken) return;
    setGeneratingQuote(true);
    setActionError('');
    try {
      const quote = await commerceApi.generateQuote(accessToken);
      navigate(`/shop/quotes/${quote.id}`);
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to generate quote');
    } finally {
      setGeneratingQuote(false);
    }
  };

  const onAttach = async (routerLineId: string, serviceId: string) => {
    try {
      await attachManagedService(serviceId, routerLineId);
      setExpandedServicePicker(null);
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to attach service');
    }
  };

  const toggleGroup = (name: string) => {
    setCollapsedGroups((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  if (collapsed) {
    return (
      <aside className="cart-drawer sb-drawer collapsed">
        <div className="cart-drawer-head collapsed-head">
          <button
            type="button"
            className="drawer-collapse-btn"
            onClick={onToggleCollapse}
            aria-label="Expand solution builder"
            title="Expand solution builder"
          >
            <PanelRight size={16} />
          </button>
          <p className="mini-note">{cart?.lines?.length || 0} items</p>
        </div>
      </aside>
    );
  }

  const renderDeviceLine = (line: CartLine, group: string) => {
    const attached = serviceLinesByRouter.get(line.id) || [];
    const isPickerOpen = expandedServicePicker === line.id;
    const compatibleServices = servicesForCategory(managedServices, line.category);
    const attachedServiceIds = new Set(attached.map((a) => a.catalog_item_id));
    const hasService = attached.length > 0;

    return (
      <div key={line.id} className="sb-line">
        <div className="sb-line-main">
          <div className="sb-thumb">
            <img
              src={getRouterImage({ id: line.catalog_item_id, name: line.item_name })}
              alt={line.item_name}
              loading="lazy"
            />
          </div>
          <div className="sb-line-info">
            <div className="sb-line-meta">
              <span className="sb-line-cat">{(line.category || group.replace(/S$/, '')).toUpperCase()}</span>
              <span className="sb-line-dot">·</span>
              <span className="sb-line-price">${line.unit_price.toFixed(2)}</span>
            </div>
            <strong className="sb-line-name">{line.item_name}</strong>
            <div className="sb-line-badges">
              {hasService ? (
                <button
                  type="button"
                  className="sb-managed-pill sb-managed-pill--on"
                  onClick={() => setExpandedServicePicker(isPickerOpen ? null : line.id)}
                  title="Managed service attached"
                >
                  <Shield size={11} />
                  Managed
                </button>
              ) : (
                <button
                  type="button"
                  className="sb-managed-pill"
                  onClick={() => setExpandedServicePicker(line.id)}
                  disabled={compatibleServices.length === 0}
                >
                  <Shield size={11} />
                  Add managed {singularLabel(group)}
                </button>
              )}
            </div>
          </div>
          <div className="sb-qty-col">
            <div className="sb-qty">
              <button
                type="button"
                className="sb-qty-btn"
                onClick={() => updateLineQuantity(line.id, Math.max(1, line.quantity - 1))}
                disabled={line.quantity <= 1}
                aria-label="Decrease quantity"
              >
                <Minus size={12} />
              </button>
              <span>{line.quantity}</span>
              <button
                type="button"
                className="sb-qty-btn"
                onClick={() => updateLineQuantity(line.id, line.quantity + 1)}
                aria-label="Increase quantity"
              >
                <Plus size={12} />
              </button>
            </div>
            <button
              type="button"
              className="sb-remove-btn"
              onClick={() => removeLine(line.id)}
              aria-label="Remove item"
              title="Remove"
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>

        {hasService && (
          <div className="sb-attached">
            {attached.map((service) => {
              const compatibleForSwap = servicesForCategory(managedServices, line.category);
              return (
                <div key={service.id} className="sb-attached-row">
                  <div className="sb-attached-head">
                    <Shield size={10} />
                    <strong>{service.item_name}</strong>
                    <span>${service.unit_price.toFixed(2)}/mo</span>
                    <button
                      type="button"
                      className="sb-attached-remove"
                      onClick={() => removeLine(service.id)}
                      aria-label="Remove service"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                  {compatibleForSwap.length > 1 && (
                    <select
                      value={service.catalog_item_id}
                      onChange={(e) => changeServiceTier(service.id, e.target.value)}
                      aria-label="Change managed service tier"
                    >
                      {compatibleForSwap.map((svc) => (
                        <option key={svc.id} value={svc.id}>
                          {svc.name} — ${svc.price.toFixed(2)}/mo
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {isPickerOpen && !hasService && (
          <div className="sb-picker">
            <div className="sb-picker-head">
              <strong>Pick a managed service</strong>
              <button
                type="button"
                className="sb-picker-close"
                onClick={() => setExpandedServicePicker(null)}
                aria-label="Close picker"
              >
                <ChevronDown size={12} style={{ transform: 'rotate(180deg)' }} />
              </button>
            </div>
            {compatibleServices.length === 0 ? (
              <p className="mini-note">No managed services available.</p>
            ) : (
              <div className="sb-picker-options">
                {compatibleServices.map((service) => {
                  const selected = attachedServiceIds.has(service.id);
                  return (
                    <button
                      key={service.id}
                      type="button"
                      className={`sb-picker-option ${selected ? 'selected' : ''}`}
                      onClick={() => onAttach(line.id, service.id)}
                    >
                      <strong>{service.name}</strong>
                      <span>${service.price.toFixed(2)}/mo</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <aside className="cart-drawer sb-drawer">
      <div className="sb-head">
        <div className="sb-head-row">
          <div className="sb-title">
            <span className="sb-title-mark"><ShoppingCart size={13} /></span>
            <h3>Solution Builder</h3>
          </div>
          <div className="sb-head-actions">
            <button type="button" className="sb-head-link">Share</button>
            <button
              type="button"
              className="sb-head-icon"
              onClick={onToggleCollapse}
              aria-label="Collapse solution builder"
              title="Collapse"
            >
              <PanelRight size={14} />
            </button>
          </div>
        </div>
        <p className="sb-subtitle">Draft #{draftNumber} · auto-saved just now</p>
      </div>

      <div className="sb-body">
        <div className="sb-bundle">
          <div className="sb-bundle-head">
            <span>Bundle discount</span>
            <span className="sb-bundle-count">{totalDeviceUnits} / {BUNDLE_GOAL} items</span>
          </div>
          <div className="sb-bundle-track">
            <div className="sb-bundle-fill" style={{ width: `${bundleProgressPct}%` }} />
          </div>
          <p className="sb-bundle-note">
            {bundleEligible
              ? `You unlocked ${Math.round(BUNDLE_DISCOUNT_RATE * 100)}% off your devices.`
              : `Add ${remainingToBundle} more ${remainingToBundle === 1 ? 'device' : 'devices'} to unlock ${Math.round((BUNDLE_DISCOUNT_RATE + 0.05) * 100)}% off.`}
          </p>
        </div>

        <div className="sb-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={activeTab === 'items'}
            className={`sb-tab ${activeTab === 'items' ? 'active' : ''}`}
            onClick={() => setActiveTab('items')}
          >
            Items <span className="sb-tab-count">{deviceLines.length}</span>
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'services'}
            className={`sb-tab ${activeTab === 'services' ? 'active' : ''}`}
            onClick={() => setActiveTab('services')}
          >
            Services
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'notes'}
            className={`sb-tab ${activeTab === 'notes' ? 'active' : ''}`}
            onClick={() => setActiveTab('notes')}
          >
            Notes
          </button>
        </div>

        {loadingCart && <div className="mini-note">Loading cart…</div>}
        {cartError && <div className="error-text">{cartError}</div>}
        {actionError && <div className="error-text">{actionError}</div>}

        {activeTab === 'items' && (
          <div className="sb-groups">
            {groupedDevices.length === 0 && (
              <p className="mini-note sb-empty">Add a device to start building your solution.</p>
            )}
            {groupedDevices.map((group) => {
              const isCollapsed = !!collapsedGroups[group.name];
              return (
                <section key={group.name} className="sb-group">
                  <header className="sb-group-head">
                    <div className="sb-group-label">
                      <span>{group.name}</span>
                      <span className="sb-group-count">{group.lines.length}</span>
                    </div>
                    <button
                      type="button"
                      className="sb-group-toggle"
                      onClick={() => toggleGroup(group.name)}
                    >
                      {isCollapsed ? 'Expand' : 'Collapse'}
                    </button>
                  </header>
                  {!isCollapsed && (
                    <div className="sb-group-body">
                      {group.lines.map((line) => renderDeviceLine(line, group.name))}
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        )}

        {activeTab === 'services' && (
          <div className="sb-services-tab">
            {standaloneServiceLines.length === 0 && serviceLinesByRouter.size === 0 && (
              <p className="mini-note sb-empty">No services yet. Attach one to a device under Items.</p>
            )}
            {Array.from(serviceLinesByRouter.entries()).map(([routerId, services]) => {
              const device = deviceLines.find((d) => d.id === routerId);
              if (!device) return null;
              return (
                <div key={routerId} className="sb-service-block">
                  <p className="sb-service-for">For {device.item_name}</p>
                  {services.map((s) => (
                    <div key={s.id} className="sb-service-item">
                      <div>
                        <strong>{s.item_name}</strong>
                        <span>${s.unit_price.toFixed(2)}/mo</span>
                      </div>
                      <button
                        type="button"
                        className="sb-remove-btn"
                        onClick={() => removeLine(s.id)}
                        aria-label="Remove service"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              );
            })}
            {standaloneServiceLines.length > 0 && (
              <div className="sb-service-block">
                <p className="sb-service-for">Standalone</p>
                {standaloneServiceLines.map((s) => (
                  <div key={s.id} className="sb-service-item">
                    <div>
                      <strong>{s.item_name}</strong>
                      <span>${s.unit_price.toFixed(2)} × {s.quantity}</span>
                    </div>
                    <button
                      type="button"
                      className="sb-remove-btn"
                      onClick={() => removeLine(s.id)}
                      aria-label="Remove service"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'notes' && (
          <div className="sb-notes-tab">
            <textarea
              className="sb-notes-area"
              placeholder="Internal notes about this solution (only you see these)…"
              rows={6}
            />
          </div>
        )}
      </div>

      <div className="sb-summary">
        <div className="sb-summary-row">
          <span>Devices subtotal</span>
          <strong>${devicesSubtotal.toFixed(2)}</strong>
        </div>
        <div className="sb-summary-row">
          <span>Managed services</span>
          <strong>+${recurringMonthly.toFixed(2)}/mo</strong>
        </div>
        {bundleEligible && bundleDiscountAmount > 0 && (
          <div className="sb-summary-row sb-summary-discount">
            <span><Sparkles size={11} /> Bundle preview (−{Math.round(BUNDLE_DISCOUNT_RATE * 100)}%)</span>
            <strong>−${bundleDiscountAmount.toFixed(2)}</strong>
          </div>
        )}
        <div className="sb-summary-divider" />
        <div className="sb-summary-totals">
          <div>
            <span className="sb-total-label">TOTAL TODAY</span>
            <strong className="sb-total-value">${totalToday.toFixed(2)}</strong>
          </div>
          <div className="sb-recurring">
            <span className="sb-recurring-label">RECURRING</span>
            <strong className="sb-recurring-value">${recurringMonthly.toFixed(2)}<small>/mo</small></strong>
          </div>
        </div>
      </div>

      <div className="sb-cta-row">
        <button
          type="button"
          className="sb-checkout-btn"
          onClick={onGenerateQuote}
          disabled={generatingQuote || (cart?.lines?.length || 0) === 0}
        >
          {generatingQuote ? 'Generating…' : 'Review & checkout'}
        </button>
        <button type="button" className="sb-fav-btn" aria-label="Save as favorite">
          <Heart size={14} />
        </button>
      </div>
    </aside>
  );
};
