import { ArrowLeft, Minus, Plus, ShoppingCart, Trash2, Ticket, ArrowRight, Shield, ChevronDown, Check, Lock, RefreshCw } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CartLine, CatalogItem } from '../types/commerce';
import { getRouterImage } from '../utils/productImages';

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value || 0);

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
    addServiceToCart,
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
      setActionError(err?.response?.data?.detail || 'Failed to generate quote');
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
      setActionError(err?.response?.data?.detail || 'Failed to clear cart');
    } finally {
      setClearing(false);
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

  const totalLineCount = cart?.lines?.length || 0;

  return (
    <section className="content-wrap fade-in cp-page">
      {/* Header */}
      <div className="cp-header">
        <div>
          <Link to="/shop/routers" className="ndb-back-link"><ArrowLeft size={16} /> Continue Shopping</Link>
          <h1>
            <ShoppingCart size={22} />
            Your Cart
            <span className="cp-count">{totalLineCount} {totalLineCount === 1 ? 'item' : 'items'}</span>
          </h1>
        </div>
        {totalLineCount > 0 && (
          <button className="ghost-btn cp-clear-btn" onClick={onClearCart} disabled={clearing}>
            <Trash2 size={13} />
            {clearing ? 'Clearing...' : 'Clear cart'}
          </button>
        )}
      </div>

      {loadingCart && <div className="dh-loading-bar"><div className="dh-loading-bar-inner" /></div>}
      {cartError && <div className="onboarding-alert error">{cartError}</div>}
      {actionError && <div className="onboarding-alert error">{actionError}</div>}

      {!loadingCart && totalLineCount === 0 && (
        <div className="cp-empty">
          <ShoppingCart size={40} strokeWidth={1.2} />
          <h3>Your cart is empty</h3>
          <p>Browse the catalog or generate a network design to add items.</p>
          <div className="cp-empty-actions">
            <Link to="/shop/routers" className="primary-btn">Browse Catalog</Link>
            <Link to="/shop/designs/new" className="ghost-btn">Create Design</Link>
          </div>
        </div>
      )}

      {totalLineCount > 0 && (
        <div className="cp-grid">
          {/* Items */}
          <div className="cp-items">
            {deviceLines.length > 0 && (
              <div className="cp-section-label">Devices ({deviceLines.length})</div>
            )}
            {deviceLines.map((router) => {
              const attached = serviceLinesByRouter.get(router.id) || [];
              const compatibleServices = servicesForCategory(managedServices, router.category);
              const isPickerOpen = expandedServicePicker === router.id;
              const attachedServiceIds = new Set(attached.map((a) => a.catalog_item_id));
              const hasService = attached.length > 0;

              return (
                <article className="cp-item" key={router.id}>
                  <div className="cp-item-main">
                    <div className="cp-thumb cp-thumb-lg">
                      <img
                        src={getRouterImage({ id: router.catalog_item_id, name: router.item_name })}
                        alt={router.item_name}
                        loading="lazy"
                      />
                    </div>
                    <div className="cp-item-info">
                      <strong className="cp-item-name">{router.item_name}</strong>
                      <span className="cp-item-cat">{router.category ? router.category.toUpperCase() : 'Device'}</span>
                      <span className="cp-item-unit-price">{formatCurrency(router.unit_price)} each</span>
                    </div>
                    <div className="cp-qty-controls">
                      <button
                        className="cp-qty-btn"
                        onClick={() => updateLineQuantity(router.id, Math.max(1, router.quantity - 1))}
                        disabled={router.quantity <= 1}
                        aria-label="Decrease quantity"
                      >
                        <Minus size={12} />
                      </button>
                      <span className="cp-qty-value">{router.quantity}</span>
                      <button
                        className="cp-qty-btn"
                        onClick={() => updateLineQuantity(router.id, Math.min(5, router.quantity + 1))}
                        disabled={router.quantity >= 5}
                        aria-label="Increase quantity"
                      >
                        <Plus size={12} />
                      </button>
                    </div>
                    <strong className="cp-item-price">{formatCurrency(router.unit_price * router.quantity)}</strong>
                    <button className="cp-remove-btn" onClick={() => removeLine(router.id)} aria-label="Remove item">
                      <Trash2 size={14} />
                    </button>
                  </div>

                  <div className="cp-item-service-area">
                    {!hasService && !isPickerOpen && (
                      <button
                        className="cp-add-service-btn"
                        onClick={() => setExpandedServicePicker(router.id)}
                        disabled={compatibleServices.length === 0}
                      >
                        <Shield size={13} />
                        <span>Add managed service for this {router.category || 'device'}</span>
                        <ChevronDown size={13} />
                      </button>
                    )}

                    {hasService && (
                      <div className="cp-attached-services">
                        {attached.map((service) => {
                          const compatibleForSwap = servicesForCategory(managedServices, router.category);
                          return (
                            <div key={service.id} className="cp-service-row">
                              <div className="cp-service-badge">
                                <Shield size={13} />
                              </div>
                              <div className="cp-service-info">
                                <span className="cp-service-name">{service.item_name}</span>
                                <span className="cp-service-price">
                                  {formatCurrency(service.unit_price)}/mo × {service.quantity}
                                </span>
                              </div>
                              <div className="cp-service-controls">
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
                                <button
                                  className="cp-remove-btn cp-remove-btn-sm"
                                  onClick={() => removeLine(service.id)}
                                  aria-label="Remove service"
                                >
                                  <Trash2 size={13} />
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {isPickerOpen && (
                      <div className="cp-service-picker">
                        <div className="cp-service-picker-head">
                          <div>
                            <strong>Pick a managed service for {router.item_name}</strong>
                            <span className="mini-note">
                              Tailored to {router.category || 'this device'} — monitored 24/7, per-unit pricing
                            </span>
                          </div>
                          <button
                            className="cp-picker-close"
                            onClick={() => setExpandedServicePicker(null)}
                            aria-label="Close picker"
                          >
                            <ChevronDown size={14} style={{ transform: 'rotate(180deg)' }} />
                          </button>
                        </div>
                        {compatibleServices.length === 0 ? (
                          <p className="mini-note" style={{ padding: '8px 0' }}>
                            No managed services available for this device category.
                          </p>
                        ) : (
                          <div className="cp-service-options">
                            {compatibleServices.map((service) => {
                              const selected = attachedServiceIds.has(service.id);
                              const features = Array.isArray(service.attributes?.features)
                                ? (service.attributes.features as string[]).slice(0, 2)
                                : [];
                              return (
                                <button
                                  key={service.id}
                                  className={`cp-service-option ${selected ? 'selected' : ''}`}
                                  onClick={() => onAttach(router.id, service.id)}
                                >
                                  <div className="cp-service-option-head">
                                    <strong>{service.name}</strong>
                                    <span className="cp-service-option-price">
                                      ${service.price.toFixed(2)}<small>/mo</small>
                                    </span>
                                  </div>
                                  {features.length > 0 && (
                                    <ul className="cp-service-option-features">
                                      {features.map((f) => (
                                        <li key={f}>
                                          <Check size={10} /> {f}
                                        </li>
                                      ))}
                                    </ul>
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
                <div className="cp-section-label">Standalone Services ({standaloneServiceLines.length})</div>
                {standaloneServiceLines.map((service) => (
                  <article className="cp-item" key={service.id}>
                    <div className="cp-item-main">
                      <div className="cp-thumb cp-thumb-lg cp-thumb-service">
                        <Shield size={22} />
                      </div>
                      <div className="cp-item-info">
                        <strong className="cp-item-name">{service.item_name}</strong>
                        <span className="cp-item-cat">Managed Service</span>
                        <span className="cp-item-unit-price">{formatCurrency(service.unit_price)}/mo each</span>
                      </div>
                      <div className="cp-qty-controls">
                        <button
                          className="cp-qty-btn"
                          onClick={() => updateLineQuantity(service.id, Math.max(1, service.quantity - 1))}
                          disabled={service.quantity <= 1}
                          aria-label="Decrease quantity"
                        >
                          <Minus size={12} />
                        </button>
                        <span className="cp-qty-value">{service.quantity}</span>
                        <button
                          className="cp-qty-btn"
                          onClick={() => updateLineQuantity(service.id, service.quantity + 1)}
                          aria-label="Increase quantity"
                        >
                          <Plus size={12} />
                        </button>
                      </div>
                      <strong className="cp-item-price">{formatCurrency(service.unit_price * service.quantity)}</strong>
                      <button className="cp-remove-btn" onClick={() => removeLine(service.id)} aria-label="Remove service">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </article>
                ))}
              </>
            )}
          </div>

          {/* Summary */}
          <aside className="cp-summary">
            <h3>Order Summary</h3>
            <div className="cp-summary-body">
              <button
                className="cp-add-standalone-btn"
                onClick={async () => {
                  const firstService = managedServices[0];
                  if (!firstService) return;
                  try {
                    await addServiceToCart(firstService.id, 1);
                  } catch (err: any) {
                    setActionError(err?.response?.data?.detail || 'Failed to add standalone service');
                  }
                }}
                disabled={managedServices.length === 0}
              >
                + Add standalone service
              </button>

              <div className="cp-promo">
                <Ticket size={14} />
                <input placeholder="Enter promo code" />
                <button className="cp-promo-apply">Apply</button>
              </div>

              <div className="cp-totals">
                <div className="cp-total-row">
                  <span>One-time hardware</span>
                  <strong>{formatCurrency(cart?.one_time_subtotal || 0)}</strong>
                </div>
                <div className="cp-total-row">
                  <span>Managed services</span>
                  <strong>{formatCurrency(cart?.monthly_subtotal || 0)}/mo</strong>
                </div>
                <div className="cp-total-row">
                  <span>Setup &amp; deployment</span>
                  <strong>Included</strong>
                </div>
                <div className="cp-total-row cp-total-grand">
                  <span>12-month total</span>
                  <strong>{formatCurrency(cart?.estimated_12_month_total || 0)}</strong>
                </div>
              </div>

              <button
                className="primary-btn cp-checkout-btn"
                onClick={onGenerateQuote}
                disabled={generatingQuote || totalLineCount === 0}
              >
                {generatingQuote ? 'Generating proposal...' : 'Generate Proposal'}
                <ArrowRight size={16} />
              </button>
            </div>
            <div className="cp-trust-row">
              <div className="cp-trust-item">
                <Lock size={12} />
                <span>Secure checkout</span>
              </div>
              <div className="cp-trust-item">
                <RefreshCw size={12} />
                <span>Cancel anytime</span>
              </div>
              <div className="cp-trust-item">
                <Shield size={12} />
                <span>SOC 2 compliant</span>
              </div>
              <div className="cp-trust-item">
                <Check size={12} />
                <span>No hidden fees</span>
              </div>
            </div>
          </aside>
        </div>
      )}
    </section>
  );
};
