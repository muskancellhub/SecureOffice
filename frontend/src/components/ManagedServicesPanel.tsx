import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Shield, ToggleLeft, ToggleRight } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import type { ManagedServicesDesignSummary, ManagedServiceCategorySummary } from '../types/commerce';

interface Props {
  designId: string;
  accessToken: string;
  readOnly?: boolean;
}

export const ManagedServicesPanel = ({ designId, accessToken, readOnly }: Props) => {
  const [msData, setMsData] = useState<ManagedServicesDesignSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const data = await commerceApi.getDesignManagedServices(accessToken, designId);
      setMsData(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load managed services');
    } finally {
      setLoading(false);
    }
  }, [accessToken, designId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggleCategory = async (group: string, currentlyEnabled: boolean) => {
    if (readOnly || !msData) return;
    const config = msData.config || {};
    const enabled = new Set<string>((config as any).enabled_categories || (config as any).enabledCategories || []);

    if (currentlyEnabled) {
      enabled.delete(group);
    } else {
      enabled.add(group);
    }

    try {
      setSaving(true);
      const result = await commerceApi.updateDesignManagedServices(accessToken, designId, {
        enabledCategories: [...enabled],
        excludedItemIds: (config as any).excluded_item_ids || (config as any).excludedItemIds || [],
      });
      setMsData(result);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  const toggleExclusion = async (itemId: string, currentlyExcluded: boolean) => {
    if (readOnly || !msData) return;
    const config = msData.config || {};
    const excluded = new Set<string>((config as any).excluded_item_ids || (config as any).excludedItemIds || []);

    if (currentlyExcluded) {
      excluded.delete(itemId);
    } else {
      excluded.add(itemId);
    }

    try {
      setSaving(true);
      const result = await commerceApi.updateDesignManagedServices(accessToken, designId, {
        enabledCategories: (config as any).enabled_categories || (config as any).enabledCategories || [],
        excludedItemIds: [...excluded],
      });
      setMsData(result);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  const toggleExpand = (group: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  if (loading && !msData) return <div className="ms-panel-loading">Loading managed services...</div>;
  if (!msData) return null;

  const categories = msData.categories || [];
  const grandTotal = msData.grandTotalMonthly || 0;

  return (
    <article className="ms-panel card">
      <div className="ms-panel-header">
        <Shield size={18} />
        <h3>Managed Services</h3>
        {saving && <span className="ms-saving-indicator">Saving...</span>}
      </div>

      {error && <div className="error-text" style={{ marginBottom: 12 }}>{error}</div>}

      <p className="ms-panel-lead">
        Toggle managed services per category. All devices are included by default — deselect exceptions below.
      </p>

      <div className="ms-categories">
        {categories.map((cat: ManagedServiceCategorySummary) => (
          <div key={cat.group} className={`ms-category-card ${cat.enabled ? 'ms-enabled' : ''}`}>
            <div className="ms-category-head">
              <button
                className="ms-toggle-btn"
                onClick={() => toggleCategory(cat.group, cat.enabled)}
                disabled={readOnly || saving}
                title={cat.enabled ? 'Disable managed services' : 'Enable managed services'}
              >
                {cat.enabled
                  ? <ToggleRight size={22} className="ms-toggle-on" />
                  : <ToggleLeft size={22} className="ms-toggle-off" />}
              </button>
              <div className="ms-category-info">
                <span className="ms-category-label">{cat.groupLabel}</span>
                <span className="ms-category-count">
                  {cat.deviceCount} device{cat.deviceCount !== 1 ? 's' : ''}
                </span>
              </div>
              {cat.enabled && (
                <div className="ms-category-total">
                  <span className="ms-applied">
                    Applied to {cat.appliedCount} of {cat.deviceCount}
                  </span>
                  <span className="ms-amount">${cat.monthlyTotal.toFixed(2)}/mo</span>
                </div>
              )}
              {cat.enabled && cat.devices.length > 0 && !readOnly && (
                <button className="ms-expand-btn" onClick={() => toggleExpand(cat.group)}>
                  {expandedGroups.has(cat.group) ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <span>Exceptions</span>
                </button>
              )}
            </div>

            {cat.enabled && expandedGroups.has(cat.group) && (
              <div className="ms-exception-list">
                <p className="ms-exception-hint">Uncheck devices you want to exclude from managed services.</p>
                <table className="ms-device-table">
                  <thead>
                    <tr>
                      <th></th>
                      <th>Device</th>
                      <th>SKU</th>
                      <th>Qty</th>
                      <th>Price/mo</th>
                      <th>Line Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cat.devices.map((device) => (
                      <tr key={device.itemId} className={device.excluded ? 'ms-excluded-row' : ''}>
                        <td>
                          <input
                            type="checkbox"
                            checked={!device.excluded}
                            onChange={() => toggleExclusion(device.itemId, device.excluded)}
                            disabled={saving}
                          />
                        </td>
                        <td>{device.name}</td>
                        <td className="ms-sku">{device.sku}</td>
                        <td>{device.quantity}</td>
                        <td>${device.managedServicePrice.toFixed(2)}</td>
                        <td>
                          {device.excluded
                            ? <span className="ms-excluded-label">Excluded</span>
                            : `$${(device.managedServicePrice * device.quantity).toFixed(2)}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>

      {categories.some((c) => c.enabled) && (
        <div className="ms-grand-total">
          <span>Total Managed Services</span>
          <span className="ms-grand-amount">${grandTotal.toFixed(2)}/mo</span>
        </div>
      )}
    </article>
  );
};
