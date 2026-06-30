import { useEffect, useMemo, useState } from 'react';
import {
  ArrowRight, Camera, Headphones, Laptop, Minus, Network, Plus, Radio, RadioTower,
  Router, Server, ShieldCheck, Smartphone, Tablet, Trash2, Wifi, X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CatalogItem } from '../types/commerce';
import { extractApiError } from '../utils/extractApiError';

// Same product scope as before — devices that carry managed-service pricing,
// across the network / security / end-user-device categories.
const SERVICE_CATEGORIES = [
  'router', 'wifi_ap', 'switch', 'firewall', 'cellular_gateway',
  'security_appliance', 'camera', 'sensor',
  'laptop', 'phone', 'tablet', 'hotspot',
];

const CATEGORY_ICON: Record<string, LucideIcon> = {
  router: Router,
  wifi_ap: Wifi,
  switch: Network,
  firewall: ShieldCheck,
  cellular_gateway: RadioTower,
  security_appliance: ShieldCheck,
  camera: Camera,
  sensor: Radio,
  laptop: Laptop,
  phone: Smartphone,
  tablet: Tablet,
  hotspot: Wifi,
};

const prettyCategory = (category?: string): string => {
  if (!category) return 'Service';
  return category
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
    .replace(/\bWifi\b/, 'Wi-Fi')
    .replace(/\bAp\b/, 'AP')
    .replace(/\bSla\b/, 'SLA');
};

const formatPrice = (value: number): string =>
  '$' + new Intl.NumberFormat('en-US', {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value || 0);

const openAssistant = () => {
  const fab = document.querySelector<HTMLButtonElement>('.chatbot-fab');
  fab?.click();
};

export const ManagedServicesCatalogPage = () => {
  const { accessToken } = useAuth();
  const { cart, addComponentToCart, addRouterToCart, updateLineQuantity, removeLine } = useShop();
  const [devices, setDevices] = useState<CatalogItem[]>([]);
  // Standalone managed-service products (SERVICE type) flagged featured — shown
  // first, ahead of the per-device managed-service cards.
  const [standalone, setStandalone] = useState<CatalogItem[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CatalogItem | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    Promise.all([
      commerceApi.getCatalog(accessToken, { type: 'DEVICE', sort: 'price_low', page_size: 250 }),
      commerceApi.getCatalog(accessToken, { category: 'managed_service', sort: 'price_low', page_size: 250 }),
    ])
      .then(([deviceList, msList]) => {
        setDevices(deviceList);
        // Only the featured ("discounted") standalone managed services are pinned
        // here; legacy tier products stay out of the customer services grid.
        setStandalone(msList.filter((m) => m.attributes?.featured && m.managed_service_price != null));
      })
      .catch((err: any) => setError(extractApiError(err, 'Failed to load catalog')))
      .finally(() => setLoading(false));
  }, [accessToken]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // Lookup: catalog_item_id → cart line
  const cartLineMap = useMemo(() => {
    const map = new Map<string, { lineId: string; quantity: number }>();
    if (!cart?.lines) return map;
    for (const line of cart.lines) {
      // Standalone managed-service component lines are keyed by their product.
      if (line.product_id && line.component_type === 'MANAGED_SERVICE') {
        map.set(line.product_id, { lineId: line.id, quantity: line.quantity });
      }
    }
    return map;
  }, [cart]);

  const services = useMemo(
    () => [
      ...standalone,
      ...devices.filter(
        (d) => SERVICE_CATEGORIES.includes(d.attributes?.category || '') && d.managed_service_price != null,
      ),
    ],
    [devices, standalone],
  );

  const handleAdd = async (device: CatalogItem) => {
    try {
      setBusyId(device.id);
      // Phase 7 D4/D10: the managed service is the device's MANAGED_SERVICE
      // component, sellable standalone at the tenant's price.
      const full = accessToken ? await commerceApi.getCatalogItem(accessToken, device.id) : device;
      const msComponent = (full.components ?? []).find((c) => c.component_type === 'MANAGED_SERVICE');
      if (msComponent) {
        await addComponentToCart(msComponent.id, 1);
        setNotice(`Managed service for ${device.name} added to cart.`);
      } else {
        await addRouterToCart(device.id, 1);
        setNotice(`${device.name} added to cart.`);
      }
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to add to cart'));
    } finally {
      setBusyId(null);
    }
  };

  const handleQtyChange = async (lineId: string, deviceId: string, newQty: number) => {
    try {
      setBusyId(deviceId);
      if (newQty <= 0) {
        await removeLine(lineId);
        setNotice('Removed from cart.');
      } else {
        await updateLineQuantity(lineId, newQty);
      }
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to update quantity'));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="content-wrap fade-in managed-services-page">
      <header className="msx-header">
        <span className="msx-eyebrow"><ShieldCheck size={15} /> Managed Services</span>
        <h1>Keep your network running — we'll handle it</h1>
        <p className="msx-subtitle">
          Layer monitoring, security, and support on top of any design. Cancel anytime.
        </p>
      </header>

      {error && <div className="error-text">{error}</div>}
      {notice && <div className="msx-notice">{notice}</div>}
      {loading && <p style={{ color: 'var(--muted)' }}>Loading pricing...</p>}

      {!loading && services.length === 0 && !error && (
        <p style={{ color: 'var(--muted)' }}>No managed services available right now.</p>
      )}

      {services.length > 0 && (
        <div className="msx-grid">
          {services.map((device) => {
            const category = device.attributes?.category || '';
            const Icon = CATEGORY_ICON[category] || Server;
            const cartLine = cartLineMap.get(device.id);
            const isBusy = busyId === device.id;
            return (
              <article key={device.id} className="msx-card">
                <div className="msx-card-top">
                  <span className="msx-card-icon"><Icon size={22} /></span>
                </div>

                <h3 className="msx-card-title">{device.name}</h3>
                <span className="msx-card-tag">{prettyCategory(category)}</span>

                {device.description && (
                  <p
                    className="msx-card-desc"
                    role="button"
                    tabIndex={0}
                    title="View full description"
                    onClick={() => setDetail(device)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setDetail(device);
                      }
                    }}
                  >
                    {device.description}
                  </p>
                )}

                <div className="msx-card-divider" />

                <div className="msx-card-foot">
                  <div className="msx-price">
                    <span className="msx-price-value">{formatPrice(device.managed_service_price ?? 0)}</span>
                    <span className="msx-price-unit">per device / mo</span>
                  </div>
                  {cartLine ? (
                    <div className="msx-stepper">
                      <button
                        className="msx-stepper-btn"
                        disabled={isBusy}
                        onClick={() =>
                          cartLine.quantity <= 1
                            ? handleQtyChange(cartLine.lineId, device.id, 0)
                            : handleQtyChange(cartLine.lineId, device.id, cartLine.quantity - 1)
                        }
                      >
                        {cartLine.quantity <= 1 ? <Trash2 size={14} /> : <Minus size={14} />}
                      </button>
                      <span className="msx-stepper-value">{cartLine.quantity}</span>
                      <button
                        className="msx-stepper-btn"
                        disabled={isBusy}
                        onClick={() => handleQtyChange(cartLine.lineId, device.id, cartLine.quantity + 1)}
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                  ) : (
                    <button className="msx-add-btn" onClick={() => handleAdd(device)} disabled={isBusy}>
                      <Plus size={16} /> {isBusy ? 'Adding…' : 'Add'}
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      <aside className="msx-banner">
        <span className="msx-banner-icon"><Headphones size={22} /></span>
        <div className="msx-banner-copy">
          <strong>Need a custom service bundle?</strong>
          <span>Talk to Aria or our team to scope a tailored SLA for your sites.</span>
        </div>
        <button type="button" className="msx-banner-btn" onClick={openAssistant}>
          Talk to us <ArrowRight size={16} />
        </button>
      </aside>

      {detail && (() => {
        const category = detail.attributes?.category || '';
        const Icon = CATEGORY_ICON[category] || Server;
        const cartLine = cartLineMap.get(detail.id);
        const isBusy = busyId === detail.id;
        return (
          <div className="msx-modal-overlay" onClick={() => setDetail(null)}>
            <div className="msx-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
              <button type="button" className="msx-modal-close" aria-label="Close" onClick={() => setDetail(null)}>
                <X size={18} />
              </button>
              <span className="msx-card-icon"><Icon size={22} /></span>
              <h3 className="msx-modal-title">{detail.name}</h3>
              <span className="msx-card-tag">{prettyCategory(category)}</span>
              <p className="msx-modal-desc">{detail.description}</p>
              <div className="msx-modal-foot">
                <div className="msx-price">
                  <span className="msx-price-value">{formatPrice(detail.managed_service_price ?? 0)}</span>
                  <span className="msx-price-unit">per device / mo</span>
                </div>
                {cartLine ? (
                  <div className="msx-stepper">
                    <button
                      className="msx-stepper-btn"
                      disabled={isBusy}
                      onClick={() =>
                        cartLine.quantity <= 1
                          ? handleQtyChange(cartLine.lineId, detail.id, 0)
                          : handleQtyChange(cartLine.lineId, detail.id, cartLine.quantity - 1)
                      }
                    >
                      {cartLine.quantity <= 1 ? <Trash2 size={14} /> : <Minus size={14} />}
                    </button>
                    <span className="msx-stepper-value">{cartLine.quantity}</span>
                    <button
                      className="msx-stepper-btn"
                      disabled={isBusy}
                      onClick={() => handleQtyChange(cartLine.lineId, detail.id, cartLine.quantity + 1)}
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                ) : (
                  <button className="msx-add-btn" onClick={() => handleAdd(detail)} disabled={isBusy}>
                    <Plus size={16} /> {isBusy ? 'Adding…' : 'Add'}
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })()}
    </section>
  );
};
