import { Minus, PanelRight, Plus, ShoppingCart, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as commerceApi from '../../api/commerceApi';
import { useAuth } from '../../context/AuthContext';
import { useShop } from '../../context/ShopContext';
import type { CartLine } from '../../types/commerce';

interface CartDrawerProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const CartDrawer = ({ collapsed = false, onToggleCollapse }: CartDrawerProps) => {
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

  if (collapsed) {
    return (
      <aside className="cart-drawer storefront-cart-drawer collapsed">
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

  return (
    <aside className="cart-drawer storefront-cart-drawer">
      <div className="cart-drawer-head">
        <h3>
          <ShoppingCart size={16} />
          Solution Builder
        </h3>
        <button
          type="button"
          className="drawer-collapse-btn"
          onClick={onToggleCollapse}
          aria-label="Collapse solution builder"
          title="Collapse solution builder"
        >
          <PanelRight size={16} />
        </button>
        <p className="mini-note">{cart?.lines?.length || 0} line items</p>
      </div>

      {loadingCart && <div className="mini-note">Loading cart...</div>}
      {cartError && <div className="error-text">{cartError}</div>}
      {actionError && <div className="error-text">{actionError}</div>}

      <div className="drawer-section">
        {deviceLines.length === 0 && <p className="mini-note">Add a device to start building your solution.</p>}

        {deviceLines.map((router) => {
          const attached = serviceLinesByRouter.get(router.id) || [];
          const lineTotal = router.unit_price * router.quantity;

          return (
            <div key={router.id} className="drawer-line-card">
              <div className="line-main builder-main">
                <div className="builder-copy">
                  <div className="builder-line">
                    <strong>{router.category ? `${router.category.toUpperCase()}:` : 'Device:'}</strong> {router.item_name} x{router.quantity} - ${router.unit_price.toFixed(2)}
                  </div>
                </div>
                <button className="icon-btn" onClick={() => removeLine(router.id)} aria-label="Remove router">
                  <Trash2 size={14} />
                </button>
              </div>

              <div className="line-controls line-qty-controls">
                <button
                  className="qty-btn"
                  onClick={() => updateLineQuantity(router.id, Math.max(1, router.quantity - 1))}
                  disabled={router.quantity <= 1}
                  aria-label="Decrease quantity"
                >
                  <Minus size={12} />
                </button>
                <span>{router.quantity}</span>
                <button
                  className="qty-btn"
                  onClick={() => updateLineQuantity(router.id, Math.min(5, router.quantity + 1))}
                  disabled={router.quantity >= 5}
                  aria-label="Increase quantity"
                >
                  <Plus size={12} />
                </button>
                <strong className="line-price">${lineTotal.toFixed(2)}</strong>
              </div>

              <button className="secondary-btn" onClick={() => setSelectedRouterForModal(router.id)}>
                Add managed service
              </button>
              <p className="mini-note service-attach-note">Managed service quantity mirrors router quantity (per unit).</p>

              {attached.length > 0 && (
                <div className="attached-services-list nested-services-list">
                  {attached.map((service) => (
                    <div key={service.id} className="attached-service-item nested-service-item">
                      <div className="builder-service-copy">
                        <div className="builder-line">
                          <strong>Managed Router:</strong> {service.item_name} x{service.quantity} - ${service.unit_price.toFixed(2)}/month
                        </div>
                      </div>
                      <div className="line-controls">
                        <label>Tier</label>
                        <select value={service.catalog_item_id} onChange={(e) => changeServiceTier(service.id, e.target.value)}>
                          {managedServices.map((svc) => (
                            <option key={svc.id} value={svc.id}>
                              {svc.name}
                            </option>
                          ))}
                        </select>
                        <button className="icon-btn" onClick={() => removeLine(service.id)} aria-label="Remove service">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {standaloneServiceLines.length > 0 && (
          <div className="drawer-line-card">
            <div className="builder-line"><strong>Standalone Services</strong></div>
            {standaloneServiceLines.map((service) => (
              <div key={service.id} className="attached-service-item nested-service-item">
                <div className="builder-line">
                  {service.item_name} x{service.quantity} - ${service.unit_price.toFixed(2)} / {service.billing_cycle?.toLowerCase() || 'period'}
                </div>
                <div className="line-controls line-qty-controls">
                  <button
                    className="qty-btn"
                    onClick={() => updateLineQuantity(service.id, Math.max(1, service.quantity - 1))}
                    disabled={service.quantity <= 1}
                    aria-label="Decrease quantity"
                  >
                    <Minus size={12} />
                  </button>
                  <span>{service.quantity}</span>
                  <button
                    className="qty-btn"
                    onClick={() => updateLineQuantity(service.id, service.quantity + 1)}
                    aria-label="Increase quantity"
                  >
                    <Plus size={12} />
                  </button>
                  <button className="icon-btn" onClick={() => removeLine(service.id)} aria-label="Remove service">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="drawer-summary">
        <div>
          <span>One-time total</span>
          <strong>${(cart?.one_time_subtotal || 0).toFixed(2)}</strong>
        </div>
        <div>
          <span>Monthly total</span>
          <strong>${(cart?.monthly_subtotal || 0).toFixed(2)}</strong>
        </div>
        <div>
          <span>Projected 12-month cost</span>
          <strong>${(cart?.estimated_12_month_total || 0).toFixed(2)}</strong>
        </div>
      </div>

      <div className="drawer-actions">
        <button
          className="secondary-btn"
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
          Add standalone service
        </button>
        <button className="primary-btn" onClick={onGenerateQuote} disabled={generatingQuote || (cart?.lines?.length || 0) === 0}>
          {generatingQuote ? 'Generating...' : 'Generate Quote'}
        </button>
      </div>

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
    </aside>
  );
};
