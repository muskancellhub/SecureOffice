import { useEffect, useState } from 'react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CatalogItem } from '../types/commerce';

export const ManagedServicesCatalogPage = () => {
  const { accessToken } = useAuth();
  const { addServiceToCart } = useShop();
  const [services, setServices] = useState<CatalogItem[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [addingId, setAddingId] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    commerceApi
      .getCatalog(accessToken, { type: 'SERVICE', sort: 'price_low' })
      .then(setServices)
      .catch((err: any) => setError(err?.response?.data?.detail || 'Failed to load managed services'));
  }, [accessToken]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 1800);
    return () => window.clearTimeout(timer);
  }, [notice]);

  return (
    <section className="content-wrap fade-in">
      <div className="content-head">
        <h1>Managed Services</h1>
        <p className="lead">Services can be added standalone, attached to devices, or combined in mixed procurement.</p>
      </div>

      {error && <div className="error-text">{error}</div>}
      {notice && <div className="mini-note">{notice}</div>}

      <div className="tier-grid static">
        {services.map((service) => (
          <article key={service.id} className="tier-card static-card">
            <h3>{service.name}</h3>
            <p className="price">${service.price.toFixed(2)} / {service.billing_cycle.toLowerCase()}</p>
            <ul>
              {Array.isArray(service.attributes?.features)
                ? service.attributes.features.map((f: string) => <li key={f}>{f}</li>)
                : <li>Managed operations</li>}
            </ul>
            <button
              className="secondary-btn"
              onClick={async () => {
                try {
                  setAddingId(service.id);
                  await addServiceToCart(service.id, 1);
                  setNotice(`${service.name} added to cart.`);
                } catch (err: any) {
                  setError(err?.response?.data?.detail || 'Failed to add service');
                } finally {
                  setAddingId(null);
                }
              }}
              disabled={addingId === service.id}
            >
              {addingId === service.id ? 'Adding...' : 'Add to cart'}
            </button>
          </article>
        ))}
      </div>
    </section>
  );
};
