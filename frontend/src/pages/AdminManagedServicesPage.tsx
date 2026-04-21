import { useCallback, useEffect, useState } from 'react';
import { Search, Save } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { CatalogItem } from '../types/commerce';

const GROUP_TABS = [
  { key: 'all', label: 'All Devices' },
  { key: 'network', label: 'Network', categories: ['router', 'wifi_ap', 'switch', 'firewall', 'cellular_gateway'] },
  { key: 'security', label: 'Security', categories: ['security_appliance', 'camera', 'sensor'] },
  { key: 'end_user_devices', label: 'End User Devices', categories: ['laptop', 'phone', 'tablet', 'hotspot'] },
];

export const AdminManagedServicesPage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';

  const [devices, setDevices] = useState<CatalogItem[]>([]);
  const [editedPrices, setEditedPrices] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState('all');
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const data = await commerceApi.getCatalog(accessToken, {
        type: 'DEVICE',
        sort: 'recommended',
        page_size: 250,
      });
      setDevices(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load devices');
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => { if (isAdmin) load(); }, [isAdmin, load]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(''), 2500);
    return () => window.clearTimeout(t);
  }, [notice]);

  const filteredDevices = devices.filter((d) => {
    const cat = d.attributes?.category || '';
    if (activeTab !== 'all') {
      const tab = GROUP_TABS.find((t) => t.key === activeTab);
      if (tab?.categories && !tab.categories.includes(cat)) return false;
    }
    if (search) {
      const s = search.toLowerCase();
      if (
        !(d.name || '').toLowerCase().includes(s) &&
        !(d.sku || '').toLowerCase().includes(s) &&
        !cat.toLowerCase().includes(s)
      ) return false;
    }
    return true;
  });

  const getDisplayPrice = (device: CatalogItem): string => {
    if (editedPrices[device.id] !== undefined) return editedPrices[device.id];
    if (device.managed_service_price != null) return device.managed_service_price.toFixed(2);
    return '';
  };

  const handlePriceChange = (id: string, value: string) => {
    setEditedPrices((prev) => ({ ...prev, [id]: value }));
  };

  const handleSaveAll = async () => {
    if (!accessToken) return;
    const updates = Object.entries(editedPrices)
      .filter(([, val]) => val !== undefined)
      .map(([item_id, val]) => ({
        item_id,
        managed_service_price: val === '' ? null : parseFloat(val),
      }));

    if (updates.length === 0) {
      setNotice('No changes to save.');
      return;
    }

    setSaving(true);
    setError('');
    try {
      const result = await commerceApi.bulkUpdateManagedServicePrices(accessToken, updates);
      setNotice(`Updated ${result.updated_count} device(s).`);
      setEditedPrices({});
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save prices');
    } finally {
      setSaving(false);
    }
  };

  const dirtyCount = Object.keys(editedPrices).length;

  return (
    <section className="content-wrap fade-in">
      {!isAdmin && <div className="error-text">Admin access required.</div>}
      {isAdmin && (
        <>
          <div className="content-head">
            <h1>Admin - Managed Service Pricing</h1>
            <p className="lead">
              Set the per-device managed service price. This price is applied when managed services are enabled on a design.
            </p>
          </div>

          {error && <div className="error-text">{error}</div>}
          {notice && <div className="mini-note">{notice}</div>}

          <div className="ams-filters">
            <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)' }} />
              <input
                placeholder="Search by name or SKU..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ paddingLeft: 30, width: '100%' }}
              />
            </div>
            {GROUP_TABS.map((tab) => (
              <button
                key={tab.key}
                className={activeTab === tab.key ? 'primary-btn' : 'ghost-btn'}
                onClick={() => setActiveTab(tab.key)}
                style={{ fontSize: '0.82rem', padding: '6px 14px' }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {loading ? (
            <p style={{ color: 'var(--muted)' }}>Loading devices...</p>
          ) : (
            <>
              <table className="ams-table">
                <thead>
                  <tr>
                    <th>SKU</th>
                    <th>Name</th>
                    <th>Category</th>
                    <th>Device Price</th>
                    <th>MS Price/mo</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDevices.map((device) => (
                    <tr key={device.id}>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}>{device.sku}</td>
                      <td>{device.name}</td>
                      <td>
                        <span className="ams-category-badge">
                          {device.attributes?.category || '—'}
                        </span>
                      </td>
                      <td>${device.price.toFixed(2)}</td>
                      <td>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          className="ams-price-input"
                          placeholder="—"
                          value={getDisplayPrice(device)}
                          onChange={(e) => handlePriceChange(device.id, e.target.value)}
                        />
                      </td>
                    </tr>
                  ))}
                  {filteredDevices.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ textAlign: 'center', color: 'var(--muted)', padding: 24 }}>
                        No devices found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

              <div className="ams-actions">
                {dirtyCount > 0 && (
                  <span style={{ color: 'var(--muted)', fontSize: '0.82rem', alignSelf: 'center' }}>
                    {dirtyCount} unsaved change{dirtyCount !== 1 ? 's' : ''}
                  </span>
                )}
                <button
                  className="primary-btn"
                  onClick={handleSaveAll}
                  disabled={saving || dirtyCount === 0}
                >
                  <Save size={14} />
                  {saving ? 'Saving...' : 'Save All Changes'}
                </button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
};
