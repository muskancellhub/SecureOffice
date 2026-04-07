import { useEffect, useState } from 'react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { CatalogItem } from '../types/commerce';

export const AdminManagedServicesPage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const [services, setServices] = useState<CatalogItem[]>([]);
  const [error, setError] = useState('');
  const [savingId, setSavingId] = useState<string | null>(null);

  const load = async () => {
    if (!accessToken) return;
    try {
      const data = await commerceApi.getCatalog(accessToken, { type: 'SERVICE', service_kind: 'managed_router', sort: 'price_low' });
      setServices(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load managed services');
    }
  };

  useEffect(() => { if (isAdmin) load(); }, [accessToken, isAdmin]);

  const updateField = (id: string, updater: (svc: CatalogItem) => CatalogItem) => {
    setServices((prev) => prev.map((svc) => (svc.id === id ? updater(svc) : svc)));
  };

  const save = async (svc: CatalogItem) => {
    if (!accessToken) return;
    setSavingId(svc.id);
    setError('');
    try {
      await commerceApi.updateManagedService(accessToken, svc.id, {
        price: svc.price,
        is_active: Boolean((svc as any).is_active ?? true),
        features: Array.isArray(svc.attributes?.features) ? svc.attributes.features : [],
      });
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save service');
    } finally {
      setSavingId(null);
    }
  };

  return (
    <section className="content-wrap fade-in">
      {!isAdmin && <div className="error-text">Admin access required.</div>}
      {isAdmin && (
        <>
      <div className="content-head">
        <h1>Admin - Managed Services</h1>
        <p className="lead">Edit Bronze/Silver/Gold features, price, and activation status.</p>
      </div>

      {error && <div className="error-text">{error}</div>}

      <div className="tier-grid static">
        {services.map((svc) => (
          <div key={svc.id} className="tier-card static-card">
            <h3>{svc.name}</h3>
            <label>Monthly price</label>
            <input
              type="number"
              value={svc.price}
              onChange={(e) => updateField(svc.id, (s) => ({ ...s, price: Number(e.target.value || 0) }))}
            />

            <label>Features (one per line)</label>
            <textarea
              rows={5}
              value={Array.isArray(svc.attributes?.features) ? svc.attributes.features.join('\n') : ''}
              onChange={(e) =>
                updateField(svc.id, (s) => ({
                  ...s,
                  attributes: {
                    ...s.attributes,
                    features: e.target.value.split('\n').map((v) => v.trim()).filter(Boolean),
                  },
                }))
              }
            />

            <label className="inline-checkbox">
              <input
                type="checkbox"
                checked={Boolean((svc as any).is_active ?? true)}
                onChange={(e) => updateField(svc.id, (s) => ({ ...(s as any), is_active: e.target.checked }))}
              />
              Active
            </label>

            <button className="primary-btn" onClick={() => save(svc)} disabled={savingId === svc.id}>
              {savingId === svc.id ? 'Saving...' : 'Save'}
            </button>
          </div>
        ))}
      </div>
        </>
      )}
    </section>
  );
};
