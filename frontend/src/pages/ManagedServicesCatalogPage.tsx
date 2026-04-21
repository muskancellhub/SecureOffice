import { useEffect, useMemo, useState } from 'react';
import { Minus, Plus, Shield, ShoppingCart, Trash2 } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CatalogItem } from '../types/commerce';

const GROUP_CONFIG = [
  { key: 'network', label: 'Network', categories: ['router', 'wifi_ap', 'switch', 'firewall', 'cellular_gateway'] },
  { key: 'security', label: 'Security', categories: ['security_appliance', 'camera', 'sensor'] },
  { key: 'end_user_devices', label: 'End User Devices', categories: ['laptop', 'phone', 'tablet', 'hotspot'] },
];

export const ManagedServicesCatalogPage = () => {
  const { accessToken } = useAuth();
  const { cart, addRouterToCart, updateLineQuantity, removeLine } = useShop();
  const [devices, setDevices] = useState<CatalogItem[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    commerceApi
      .getCatalog(accessToken, { type: 'DEVICE', sort: 'price_low', page_size: 250 })
      .then(setDevices)
      .catch((err: any) => setError(err?.response?.data?.detail || 'Failed to load catalog'))
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
      map.set(line.catalog_item_id, { lineId: line.id, quantity: line.quantity });
    }
    return map;
  }, [cart]);

  const handleAdd = async (device: CatalogItem) => {
    try {
      setBusyId(device.id);
      await addRouterToCart(device.id, 1);
      setNotice(`${device.name} added to cart.`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to add to cart');
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
      setError(err?.response?.data?.detail || 'Failed to update quantity');
    } finally {
      setBusyId(null);
    }
  };

  const devicesByGroup = GROUP_CONFIG.map((group) => {
    const items = devices.filter(
      (d) => group.categories.includes(d.attributes?.category || '') && d.managed_service_price != null
    );
    return { ...group, items };
  });

  return (
    <section className="content-wrap fade-in">
      <div className="content-head">
        <h1>Managed Services</h1>
        <p className="lead">
          Browse devices with managed service pricing. Add to cart and managed services
          will be applied automatically based on per-device pricing.
        </p>
      </div>

      {error && <div className="error-text">{error}</div>}
      {notice && <div className="mini-note">{notice}</div>}
      {loading && <p style={{ color: 'var(--muted)' }}>Loading pricing...</p>}

      {!loading && devicesByGroup.map((group) => (
        <article key={group.key} className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Shield size={16} />
            <h3 style={{ margin: 0 }}>{group.label}</h3>
            <span style={{ fontSize: '0.78rem', color: 'var(--muted)', marginLeft: 'auto' }}>
              {group.items.length} device{group.items.length !== 1 ? 's' : ''} with pricing
            </span>
          </div>

          {group.items.length === 0 ? (
            <p style={{ color: 'var(--muted)', fontSize: '0.88rem' }}>
              No devices with managed service pricing in this category.
            </p>
          ) : (
            <table className="ms-device-table">
              <thead>
                <tr>
                  <th>Device</th>
                  <th>SKU</th>
                  <th>Category</th>
                  <th>MS Price/mo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {group.items.map((device) => {
                  const cartLine = cartLineMap.get(device.id);
                  const isBusy = busyId === device.id;
                  return (
                    <tr key={device.id}>
                      <td>{device.name}</td>
                      <td className="ms-sku">{device.sku}</td>
                      <td>
                        <span className="ams-category-badge">{device.attributes?.category || '—'}</span>
                      </td>
                      <td style={{ fontWeight: 600, color: 'var(--primary)' }}>
                        ${(device.managed_service_price ?? 0).toFixed(2)}
                      </td>
                      <td>
                        {cartLine ? (
                          <div className="qty-stepper">
                            <button
                              className="qty-stepper-btn"
                              disabled={isBusy}
                              onClick={() =>
                                cartLine.quantity <= 1
                                  ? handleQtyChange(cartLine.lineId, device.id, 0)
                                  : handleQtyChange(cartLine.lineId, device.id, cartLine.quantity - 1)
                              }
                            >
                              {cartLine.quantity <= 1 ? <Trash2 size={13} /> : <Minus size={13} />}
                            </button>
                            <span className="qty-stepper-value">{cartLine.quantity}</span>
                            <button
                              className="qty-stepper-btn"
                              disabled={isBusy}
                              onClick={() => handleQtyChange(cartLine.lineId, device.id, cartLine.quantity + 1)}
                            >
                              <Plus size={13} />
                            </button>
                          </div>
                        ) : (
                          <button
                            className="secondary-btn"
                            style={{ fontSize: '0.78rem', padding: '5px 10px', display: 'flex', alignItems: 'center', gap: 4 }}
                            onClick={() => handleAdd(device)}
                            disabled={isBusy}
                          >
                            <ShoppingCart size={13} />
                            {isBusy ? 'Adding...' : 'Add to Cart'}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </article>
      ))}
    </section>
  );
};
