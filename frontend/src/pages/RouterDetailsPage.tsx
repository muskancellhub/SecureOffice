import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CatalogItem } from '../types/commerce';
import { getRouterImage } from '../utils/productImages';

export const RouterDetailsPage = () => {
  const { itemId } = useParams();
  const { accessToken } = useAuth();
  const { addRouterToCart } = useShop();
  const [router, setRouter] = useState<CatalogItem | null>(null);
  const [qty, setQty] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [addedNotice, setAddedNotice] = useState('');

  useEffect(() => {
    if (!accessToken || !itemId) return;
    setLoading(true);
    commerceApi
      .getCatalogItem(accessToken, itemId)
      .then(setRouter)
      .catch((err: any) => setError(err?.response?.data?.detail || 'Failed to load router details'))
      .finally(() => setLoading(false));
  }, [accessToken, itemId]);

  useEffect(() => {
    if (!addedNotice) return;
    const timer = window.setTimeout(() => setAddedNotice(''), 1500);
    return () => window.clearTimeout(timer);
  }, [addedNotice]);

  const specs = router?.attributes?.specs || {};

  return (
    <section className="content-wrap fade-in">
      <div className="content-head row-between">
        <h1>Router Details</h1>
        <Link to="/shop/routers" className="ghost-link">Back to catalog</Link>
      </div>

      {loading && <div className="mini-note">Loading details...</div>}
      {error && <div className="error-text">{error}</div>}

      {router && (
        <div className="details-card">
          <div className="details-image">
            <img
              src={getRouterImage({
                id: router.id,
                sku: router.sku,
                name: router.name,
                brand: String(router.attributes?.brand || ''),
                model: String(router.attributes?.model || ''),
                imageUrl: String(router.attributes?.image_url || ''),
              })}
              alt={router.name}
              className="product-image"
            />
          </div>
          <div>
            <h2>{router.name}</h2>
            <p className="sku">SKU: {router.sku}</p>
            <p>{router.description || 'No description available.'}</p>
            <div className="row-between">
              <strong className="price">${router.price.toFixed(2)} {router.currency}</strong>
              <span className={`badge ${(router.availability || '').toLowerCase().includes('stock') ? 'ok' : 'warn'}`}>
                {router.availability || 'Unknown'}
              </span>
            </div>

            <h4>Specifications</h4>
            <ul className="spec-bullets">
              <li>Brand: {router.attributes?.brand || 'N/A'}</li>
              <li>Model: {router.attributes?.model || 'N/A'}</li>
              <li>Ports: {typeof router.attributes?.ports === 'object' ? JSON.stringify(router.attributes?.ports) : (router.attributes?.ports || 'N/A')}</li>
              <li>Wi-Fi Standard: {router.attributes?.wifi_standard || 'N/A'}</li>
              {Object.entries(specs).slice(0, 6).map(([k, v]) => <li key={k}>{k}: {String(v)}</li>)}
            </ul>

            <div className="inline-fields compact">
              <label>Quantity</label>
              <select value={qty} onChange={(e) => setQty(Number(e.target.value))}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>

            <button
              className="primary-btn"
              onClick={async () => {
                try {
                  await addRouterToCart(router.id, qty);
                  setAddedNotice('Added to cart');
                } catch (err: any) {
                  setError(err?.response?.data?.detail || 'Failed to add item to cart');
                }
              }}
            >
              Add to cart
            </button>
          </div>
        </div>
      )}
      {addedNotice && <div className="toast-notice">{addedNotice}</div>}
    </section>
  );
};
