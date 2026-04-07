import { ArrowLeft, Minus, Plus, ShoppingCart, Trash2, Ticket, ArrowRight } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CartLine } from '../types/commerce';
import { getRouterImage } from '../utils/productImages';

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value || 0);

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

  const [selectedRouterForModal, setSelectedRouterForModal] = useState<string | null>(null);
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

  const selectedRouter = deviceLines.find((r) => r.id === selectedRouterForModal) || null;
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
              return (
                <article className="cp-item" key={router.id}>
                  <div className="cp-item-main">
                    <div className="cp-thumb">
                      <img
                        src={getRouterImage({ id: router.catalog_item_id, name: router.item_name })}
                        alt={router.item_name}
                        loading="lazy"
                      />
                    </div>
                    <div className="cp-item-info">
                      <strong className="cp-item-name">{router.item_name}</strong>
                      <span className="cp-item-cat">{router.category ? router.category.toUpperCase() : 'Device'}</span>
                    </div>
                    <div className="cp-qty-controls">
                      <button
                        className="cp-qty-btn"
                        onClick={() => updateLineQuantity(router.id, Math.max(1, router.quantity - 1))}
                        disabled={router.quantity <= 1}
                      >
                        <Minus size={12} />
                      </button>
                      <span className="cp-qty-value">{router.quantity}</span>
                      <button
                        className="cp-qty-btn"
                        onClick={() => updateLineQuantity(router.id, Math.min(5, router.quantity + 1))}
                        disabled={router.quantity >= 5}
                      >
                        <Plus size={12} />
                      </button>
                    </div>
                    <strong className="cp-item-price">{formatCurrency(router.unit_price * router.quantity)}</strong>
                    <button className="cp-remove-btn" onClick={() => removeLine(router.id)}>
                      <Trash2 size={14} />
                    </button>
                  </div>

                  <div className="cp-item-service-area">
                    <button className="cp-add-service-btn" onClick={() => setSelectedRouterForModal(router.id)}>
                      + Add managed service
                    </button>
                    {attached.length > 0 && (
                      <div className="cp-attached-services">
                        {attached.map((service) => (
                          <div key={service.id} className="cp-service-row">
                            <div className="cp-service-info">
                              <span className="cp-service-name">{service.item_name}</span>
                              <span className="cp-service-price">{formatCurrency(service.unit_price)}/mo</span>
                            </div>
                            <div className="cp-service-controls">
                              <select value={service.catalog_item_id} onChange={(e) => changeServiceTier(service.id, e.target.value)}>
                                {managedServices.map((svc) => (
                                  <option key={svc.id} value={svc.id}>{svc.name}</option>
                                ))}
                              </select>
                              <button className="cp-remove-btn" onClick={() => removeLine(service.id)}>
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                        ))}
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
                      <div className="cp-item-info">
                        <strong className="cp-item-name">{service.item_name}</strong>
                        <span className="cp-item-cat">Managed Service</span>
                      </div>
                      <div className="cp-qty-controls">
                        <button
                          className="cp-qty-btn"
                          onClick={() => updateLineQuantity(service.id, Math.max(1, service.quantity - 1))}
                          disabled={service.quantity <= 1}
                        >
                          <Minus size={12} />
                        </button>
                        <span className="cp-qty-value">{service.quantity}</span>
                        <button
                          className="cp-qty-btn"
                          onClick={() => updateLineQuantity(service.id, service.quantity + 1)}
                        >
                          <Plus size={12} />
                        </button>
                      </div>
                      <strong className="cp-item-price">{formatCurrency(service.unit_price * service.quantity)}</strong>
                      <button className="cp-remove-btn" onClick={() => removeLine(service.id)}>
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
              <input placeholder="Promo code" />
              <button className="cp-promo-apply">Apply</button>
            </div>

            <div className="cp-totals">
              <div className="cp-total-row">
                <span>Subtotal</span>
                <strong>{formatCurrency(cart?.one_time_subtotal || 0)}</strong>
              </div>
              <div className="cp-total-row">
                <span>Discount</span>
                <span>-$0.00</span>
              </div>
              <div className="cp-total-row cp-total-grand">
                <span>Total</span>
                <strong>{formatCurrency(cart?.estimated_12_month_total || 0)}</strong>
              </div>
            </div>

            <button className="primary-btn cp-checkout-btn" onClick={onGenerateQuote} disabled={generatingQuote || totalLineCount === 0}>
              {generatingQuote ? 'Generating...' : 'Generate Proposal'}
              <ArrowRight size={14} />
            </button>
          </aside>
        </div>
      )}

      {/* Service Modal */}
      {selectedRouter && (
        <div className="modal-overlay" onClick={() => setSelectedRouterForModal(null)}>
          <div className="tier-modal" onClick={(e) => e.stopPropagation()}>
            <h4>Attach Managed Service</h4>
            <p className="mini-note">Attach to: {selectedRouter.item_name}</p>
            <div className="tier-grid">
              {managedServices.map((service) => (
                <button
                  key={service.id}
                  className="tier-card"
                  onClick={async () => {
                    try {
                      await attachManagedService(service.id, selectedRouter.id);
                      setSelectedRouterForModal(null);
                    } catch (err: any) {
                      setActionError(err?.response?.data?.detail || 'Failed to attach service');
                    }
                  }}
                >
                  <h5>{service.name}</h5>
                  <p className="price">${service.price.toFixed(2)}/mo</p>
                  <ul>
                    {Array.isArray(service.attributes?.features) ? (
                      service.attributes.features.slice(0, 3).map((f: string) => <li key={f}>{f}</li>)
                    ) : (
                      <li>Managed operations</li>
                    )}
                  </ul>
                </button>
              ))}
            </div>
            <button className="ghost-btn" onClick={() => setSelectedRouterForModal(null)}>
              Close
            </button>
          </div>
        </div>
      )}
    </section>
  );
};
