import { ArrowLeft, Minus, Plus, ShoppingCart, Trash2, ArrowRight, ShieldCheck, ChevronDown, Check, Lock, RefreshCw, Router as RouterIcon, Wifi, Network, RadioTower, Laptop, Smartphone, Server } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CartLine, CatalogItem } from '../types/commerce';
import { extractApiError } from '../utils/extractApiError';

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value || 0);

const CATEGORY_ICON: Record<string, { icon: LucideIcon; tone: string }> = {
  router: { icon: RouterIcon, tone: 'blue' }, wifi_ap: { icon: Wifi, tone: 'blue' }, switch: { icon: Network, tone: 'blue' },
  firewall: { icon: ShieldCheck, tone: 'blue' }, security_appliance: { icon: ShieldCheck, tone: 'blue' },
  cellular_gateway: { icon: RadioTower, tone: 'amber' }, hotspot: { icon: RadioTower, tone: 'amber' },
  laptop: { icon: Laptop, tone: 'violet' }, tablet: { icon: Laptop, tone: 'violet' }, phone: { icon: Smartphone, tone: 'violet' },
};
const deviceViz = (category?: string | null) => CATEGORY_ICON[(category || '').toLowerCase()] || { icon: Server, tone: 'blue' };

// Turn a raw category slug (e.g. "cellular_gateway") into a readable label
// ("Cellular gateway") for the managed-service card subtitle.
const prettyCategory = (category: string | null | undefined): string => {
  if (!category) return '';
  const spaced = category.replace(/_/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
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

export const CartPage = () => {
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

  const [expandedServicePicker, setExpandedServicePicker] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const [generatingQuote, setGeneratingQuote] = useState(false);
  const [clearing, setClearing] = useState(false);

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

  const onGenerateQuote = async () => {
    if (!accessToken) return;
    setGeneratingQuote(true);
    setActionError('');
    try {
      const quote = await commerceApi.generateQuote(accessToken);
      navigate(`/shop/quotes/${quote.id}`);
    } catch (err: any) {
      setActionError(extractApiError(err, 'Failed to generate quote'));
    } finally {
      setGeneratingQuote(false);
    }
  };

  const onClearCart = async () => {
    const lineIds = (cart?.lines || []).map((line) => line.id);
    if (lineIds.length === 0) return;

    setClearing(true);
    setActionError('');
    try {
      for (const lineId of lineIds) {
        await removeLine(lineId);
      }
    } catch (err: any) {
      setActionError(extractApiError(err, 'Failed to clear cart'));
    } finally {
      setClearing(false);
    }
  };

  const onAttach = async (routerLineId: string, serviceId: string) => {
    try {
      await attachManagedService(serviceId, routerLineId);
      setExpandedServicePicker(null);
    } catch (err: any) {
      setActionError(extractApiError(err, 'Failed to attach service'));
    }
  };

  const totalLineCount = cart?.lines?.length || 0;

  return (
    <section className="content-wrap fade-in cpx-page">
      <header className="cpx-header">
        <div>
          <Link to="/shop/routers" className="cdx-back"><ArrowLeft size={15} /> Continue shopping</Link>
          <h1>Your cart <span className="cpx-count">{totalLineCount} {totalLineCount === 1 ? 'item' : 'items'}</span></h1>
        </div>
        {totalLineCount > 0 && (
          <button className="cpx-clear" onClick={onClearCart} disabled={clearing}>
            <Trash2 size={15} /> {clearing ? 'Clearing…' : 'Clear cart'}
          </button>
        )}
      </header>

      {loadingCart && <div className="dh-loading-bar"><div className="dh-loading-bar-inner" /></div>}
      {cartError && <div className="onboarding-alert error">{cartError}</div>}
      {actionError && <div className="onboarding-alert error">{actionError}</div>}

      {!loadingCart && totalLineCount === 0 && (
        <div className="cpx-empty">
          <span className="cpx-empty-ico"><ShoppingCart size={30} strokeWidth={1.3} /></span>
          <h3>Your cart is empty</h3>
          <p>Browse the catalog or generate a network design to add items.</p>
          <div className="cpx-empty-actions">
            <Link to="/shop/routers" className="apx-add-btn">Browse catalog</Link>
            <Link to="/shop/designs/new" className="dnb-tool-btn">Create design</Link>
          </div>
        </div>
      )}

      {totalLineCount > 0 && (
        <div className="cpx-grid">
          <div className="cpx-items">
            {deviceLines.length > 0 && <div className="cpx-section-label">Devices · {deviceLines.length}</div>}
            {deviceLines.map((router) => {
              const attached = serviceLinesByRouter.get(router.id) || [];
              const compatibleServices = servicesForCategory(managedServices, router.category);
              const isPickerOpen = expandedServicePicker === router.id;
              const attachedServiceIds = new Set(attached.map((a) => a.catalog_item_id));
              const hasService = attached.length > 0;
              const viz = deviceViz(router.category);
              const VizIcon = viz.icon;

              return (
                <article className="cpx-item" key={router.id}>
                  <div className="cpx-item-main">
                    <span className={`cpx-thumb tone-${viz.tone}`}><VizIcon size={22} /></span>
                    <div className="cpx-item-info">
                      <strong>{router.item_name}</strong>
                      <span className="cpx-item-cat">{router.category ? router.category.replace(/_/g, ' ') : 'Device'} · {formatCurrency(router.unit_price)} each</span>
                    </div>
                    <div className="cpx-qty">
                      <button className="cpx-qty-btn" onClick={() => updateLineQuantity(router.id, Math.max(1, router.quantity - 1))} disabled={router.quantity <= 1} aria-label="Decrease"><Minus size={14} /></button>
                      <span className="cpx-qty-val">{router.quantity}</span>
                      <button className="cpx-qty-btn" onClick={() => updateLineQuantity(router.id, Math.min(5, router.quantity + 1))} disabled={router.quantity >= 5} aria-label="Increase"><Plus size={14} /></button>
                    </div>
                    <strong className="cpx-item-price">{formatCurrency(router.unit_price * router.quantity)}</strong>
                    <button className="cpx-remove" onClick={() => removeLine(router.id)} aria-label="Remove"><Trash2 size={16} /></button>
                  </div>

                  <div className="cpx-svc-area">
                    {!hasService && !isPickerOpen && (
                      <button className="cpx-add-svc" onClick={() => setExpandedServicePicker(router.id)} disabled={compatibleServices.length === 0}>
                        <ShieldCheck size={14} /> <span>Add managed service for this {router.category || 'device'}</span> <ChevronDown size={14} />
                      </button>
                    )}

                    {hasService && (
                      <div className="cpx-attached">
                        {attached.map((service) => {
                          const compatibleForSwap = servicesForCategory(managedServices, router.category);
                          return (
                            <div key={service.id} className="cpx-svc-row">
                              <span className="cpx-svc-badge"><ShieldCheck size={14} /></span>
                              <div className="cpx-svc-info">
                                <span className="cpx-svc-name">{service.item_name}</span>
                                <span className="cpx-svc-price">{formatCurrency(service.unit_price)}/mo × {service.quantity}</span>
                              </div>
                              <select value={service.catalog_item_id} onChange={(e) => changeServiceTier(service.id, e.target.value)} aria-label="Change tier">
                                {compatibleForSwap.map((svc) => <option key={svc.id} value={svc.id}>{svc.name} — ${svc.price.toFixed(2)}/mo</option>)}
                              </select>
                              <button className="cpx-remove cpx-remove-sm" onClick={() => removeLine(service.id)} aria-label="Remove service"><Trash2 size={14} /></button>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {isPickerOpen && (
                      <div className="cpx-picker">
                        <div className="cpx-picker-head">
                          <div>
                            <strong>Pick a managed service</strong>
                            <span>Tailored to {router.category || 'this device'} — monitored 24/7</span>
                          </div>
                          <button className="cpx-picker-close" onClick={() => setExpandedServicePicker(null)} aria-label="Close"><ChevronDown size={16} style={{ transform: 'rotate(180deg)' }} /></button>
                        </div>
                        {compatibleServices.length === 0 ? (
                          <p className="cpx-note">No managed services available for this device category.</p>
                        ) : (
                          <div className="cpx-svc-opts">
                            {compatibleServices.map((service) => {
                              const selected = attachedServiceIds.has(service.id);
                              const features = Array.isArray(service.attributes?.features) ? (service.attributes.features as string[]).slice(0, 2) : [];
                              return (
                                <button key={service.id} className={`cpx-svc-opt ${selected ? 'selected' : ''}`} onClick={() => onAttach(router.id, service.id)}>
                                  <div className="cpx-svc-opt-head"><strong>{service.name}</strong><span>${service.price.toFixed(2)}<small>/mo</small></span></div>
                                  {features.length > 0 && (
                                    <ul className="cpx-svc-opt-feat">{features.map((f) => <li key={f}><Check size={11} /> {f}</li>)}</ul>
                                  )}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </article>
              );
            })}

            {standaloneServiceLines.length > 0 && (
              <>
                <div className="cpx-section-label"><RefreshCw size={13} /> Managed services · {standaloneServiceLines.length}</div>
                {standaloneServiceLines.map((service) => {
                  const category = prettyCategory(service.category);
                  const subtitle = [category, 'fully managed'].filter(Boolean).join(' · ');
                  return (
                    <article className="cpx-item cpx-ms" key={service.id}>
                      <div className="cpx-item-main">
                        <span className="cpx-thumb tone-pink"><ShieldCheck size={22} /></span>
                        <div className="cpx-item-info">
                          <strong>{service.item_name}</strong>
                          {subtitle && <span className="cpx-item-cat">{subtitle}</span>}
                        </div>
                        <strong className="cpx-item-price">{formatCurrency(service.unit_price * service.quantity)}<small>/mo</small></strong>
                        <button className="cpx-remove" onClick={() => removeLine(service.id)} aria-label="Remove service"><Trash2 size={16} /></button>
                      </div>
                    </article>
                  );
                })}
              </>
            )}
          </div>

          <aside className="cpx-summary">
            <h3>Order summary</h3>
            <button className="cpx-add-standalone" onClick={() => navigate('/shop/services')}>
              <ShieldCheck size={14} /> <span>Add standalone service</span> <ArrowRight size={14} />
            </button>
            <div className="cpx-totals">
              <div className="cpx-total-row"><span>One-time hardware</span><strong>{formatCurrency(cart?.one_time_subtotal || 0)}</strong></div>
              <div className="cpx-total-row"><span>Managed services</span><strong>{formatCurrency(cart?.monthly_subtotal || 0)}/mo</strong></div>
              <div className="cpx-total-row"><span>Setup &amp; deployment</span><strong>Included</strong></div>
              <div className="cpx-total-row cpx-grand"><span>12-month total</span><strong>{formatCurrency(cart?.estimated_12_month_total || 0)}</strong></div>
            </div>
            <button className="cpx-checkout" onClick={onGenerateQuote} disabled={generatingQuote || totalLineCount === 0}>
              {generatingQuote ? 'Generating…' : 'Generate proposal'} <ArrowRight size={17} />
            </button>
            <div className="cpx-trust">
              <span><Lock size={13} /> Secure checkout</span>
              <span><RefreshCw size={13} /> Cancel anytime</span>
              <span><ShieldCheck size={13} /> SOC 2 compliant</span>
              <span><Check size={13} /> No hidden fees</span>
            </div>
          </aside>
        </div>
      )}
    </section>
  );
};
