import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Laptop, Minus, Network, Plus, RadioTower, Router as RouterIcon, Server, ShieldCheck, ShoppingCart, Smartphone, Wifi } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import BundleConfigurator from '../components/BundleConfigurator';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CatalogItem } from '../types/commerce';
import { getRouterImage } from '../utils/productImages';
import { extractApiError } from '../utils/extractApiError';

const CATEGORY_ICON: Record<string, { icon: LucideIcon; tone: string }> = {
  router: { icon: RouterIcon, tone: 'blue' }, wifi_ap: { icon: Wifi, tone: 'blue' }, switch: { icon: Network, tone: 'blue' },
  firewall: { icon: ShieldCheck, tone: 'blue' }, security_appliance: { icon: ShieldCheck, tone: 'blue' },
  cellular_gateway: { icon: RadioTower, tone: 'amber' }, hotspot: { icon: RadioTower, tone: 'amber' },
  laptop: { icon: Laptop, tone: 'violet' }, tablet: { icon: Laptop, tone: 'violet' }, phone: { icon: Smartphone, tone: 'violet' },
};

const money = (v: number): string => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(v || 0);
const prettyKey = (k: string): string => k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export const RouterDetailsPage = () => {
  const { itemId } = useParams();
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const { addProductToCart } = useShop();
  const [item, setItem] = useState<CatalogItem | null>(null);
  const [qty, setQty] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);
  const [showConfigurator, setShowConfigurator] = useState(false);
  const [goToCartAfterAdd, setGoToCartAfterAdd] = useState(false);

  useEffect(() => {
    if (!accessToken || !itemId) return;
    setLoading(true);
    commerceApi
      .getCatalogItem(accessToken, itemId)
      .then(setItem)
      .catch((err: any) => setError(extractApiError(err, 'Failed to load product details')))
      .finally(() => setLoading(false));
  }, [accessToken, itemId]);

  const specEntries = useMemo(() => {
    if (!item) return [] as [string, string][];
    const specs = (item.attributes?.specs && typeof item.attributes.specs === 'object') ? item.attributes.specs : null;
    if (specs && Object.keys(specs).length) {
      return Object.entries(specs).slice(0, 8).map(([k, v]) => [prettyKey(k), String(v)] as [string, string]);
    }
    const fallback: [string, string][] = [];
    if (item.attributes?.brand) fallback.push(['Brand', String(item.attributes.brand)]);
    if (item.attributes?.model) fallback.push(['Model', String(item.attributes.model)]);
    if (item.attributes?.ports != null) fallback.push(['Ports', typeof item.attributes.ports === 'object' ? JSON.stringify(item.attributes.ports) : String(item.attributes.ports)]);
    if (item.attributes?.wifi_standard) fallback.push(['Wi-Fi standard', String(item.attributes.wifi_standard)]);
    return fallback;
  }, [item]);

  const hasBundle = (item?.components?.length ?? 0) > 1;

  const onAdd = async () => {
    if (!item) return;
    if (hasBundle) {
      // Phase 7 D9: bundled solutions configure before landing in the cart.
      setGoToCartAfterAdd(false);
      setShowConfigurator(true);
      return;
    }
    setBusy(true);
    try {
      await addProductToCart(item.product_id ?? item.id, { quantity: qty });
    } finally {
      setBusy(false);
    }
  };

  const onBuyNow = async () => {
    if (!item) return;
    if (hasBundle) {
      setGoToCartAfterAdd(true);
      setShowConfigurator(true);
      return;
    }
    setBusy(true);
    try {
      await addProductToCart(item.product_id ?? item.id, { quantity: qty });
      navigate('/shop/cart');
    } finally {
      setBusy(false);
    }
  };

  const viz = item ? (CATEGORY_ICON[item.attributes?.category || ''] || { icon: Server, tone: 'blue' }) : { icon: Server, tone: 'blue' };
  const Icon = viz.icon;
  const stockOk = !(item?.availability || 'in_stock').toLowerCase().includes('back');
  const papiImage = String(item?.attributes?.image_url || '').trim();
  const imageSrc = item && papiImage && !imgFailed
    ? getRouterImage({ id: item.id, sku: item.sku, name: item.name, brand: String(item.attributes?.brand || ''), model: String(item.attributes?.model || ''), imageUrl: papiImage })
    : '';

  return (
    <section className="content-wrap fade-in cdx-page">
      <Link to="/shop/routers" className="cdx-back"><ArrowLeft size={16} /> Catalog</Link>

      {loading && <div className="cat2-note">Loading details…</div>}
      {error && <div className="error-text">{error}</div>}

      {item && (
        <div className="cdx-layout">
          <div className="cdx-gallery">
            <div className={`cdx-viz tone-${viz.tone}`}>
              {imageSrc ? (
                <img className="cdx-img" src={imageSrc} alt={item.name} onError={() => setImgFailed(true)} />
              ) : (
                <span className="cdx-viz-icon"><Icon size={44} /></span>
              )}
            </div>
            <div className="cdx-thumbs">
              {[0, 1, 2, 3].map((i) => <span key={i} className="cdx-thumb" />)}
            </div>
          </div>

          <div className="cdx-info">
            <div className="cdx-brand-row">
              <span className="cdx-brand">{String(item.attributes?.brand || item.vendor || 'Catalog')}</span>
              {item.attributes?.badge && <span className="cdx-tag">{String(item.attributes.badge)}</span>}
            </div>
            <h1 className="cdx-title">{item.name}</h1>
            <div className="cdx-sku-row">
              <span className="cdx-sku">SKU {item.sku}</span>
              <span className={`cdx-stock ${stockOk ? 'green' : 'amber'}`}>{stockOk ? 'In stock' : 'Backorder'}</span>
            </div>

            <div className="cdx-price-row">
              <span className="cdx-price">{money(item.price)}</span>
              {item.managed_service_price != null && (
                <span className="cdx-managed"><ShieldCheck size={14} /> Managed from $ {item.managed_service_price.toFixed(0)} <small>/mo</small></span>
              )}
            </div>

            {specEntries.length > 0 && (
              <div className="cdx-specs">
                <h3>Specifications</h3>
                <div className="cdx-spec-grid">
                  {specEntries.map(([k, v]) => (
                    <div key={k} className="cdx-spec">
                      <span className="cdx-spec-k">{k}</span>
                      <span className="cdx-spec-v">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {item.description && <p className="cdx-desc">{item.description}</p>}

            {Array.isArray(item.attributes?.services_table?.rows) && (
              <div className="cdx-svc">
                <h3>Core services</h3>
                <table className="cdx-svc-table">
                  <thead>
                    <tr>
                      {(item.attributes.services_table.columns as string[]).map((c) => (
                        <th key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(item.attributes.services_table.rows as string[][]).map((row, ri) => (
                      <tr key={ri}>
                        {row.map((cell, ci) => <td key={ci}>{cell}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {Array.isArray(item.attributes?.detail_sections) && (
              <div className="cdx-details">
                {(item.attributes.detail_sections as { heading: string; items: string[] }[]).map((sec) => (
                  <div key={sec.heading} className="cdx-detail-sec">
                    <h3>{sec.heading}</h3>
                    <ul className="cdx-detail-list">
                      {sec.items.map((li, i) => <li key={i}>{li}</li>)}
                    </ul>
                  </div>
                ))}
              </div>
            )}

            <div className="cdx-buy-row">
              <div className="cdx-qty">
                <button className="cdx-qty-btn" aria-label="Decrease" onClick={() => setQty((q) => Math.max(1, q - 1))}><Minus size={15} /></button>
                <span className="cdx-qty-val">{qty}</span>
                <button className="cdx-qty-btn" aria-label="Increase" onClick={() => setQty((q) => q + 1)}><Plus size={15} /></button>
              </div>
              <button className="cdx-add" onClick={onAdd} disabled={busy}>
                <ShoppingCart size={17} /> Add to cart · {money(item.price * qty)}
              </button>
            </div>
            <button className="cdx-buynow" onClick={onBuyNow} disabled={busy}>Buy now</button>
          </div>
        </div>
      )}

      {item && showConfigurator && (
        <BundleConfigurator
          product={item}
          onClose={() => setShowConfigurator(false)}
          onConfirm={async (selections, financialModel, interval) => {
            await addProductToCart(item.product_id ?? item.id, {
              selections, financialModel, interval, quantity: qty,
            });
            if (goToCartAfterAdd) navigate('/shop/cart');
          }}
        />
      )}
    </section>
  );
};
