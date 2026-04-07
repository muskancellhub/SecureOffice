import { useEffect, useState } from 'react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { AssetSummary, ContractSummary, SubscriptionStatus, SubscriptionSummary } from '../types/commerce';

const statusOptions: SubscriptionStatus[] = ['ACTIVE', 'PAUSED', 'CANCELLED'];

export const LifecyclePage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionSummary[]>([]);
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingSubscriptionId, setSavingSubscriptionId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    try {
      const [contractRows, subscriptionRows, assetRows] = await Promise.all([
        commerceApi.listContracts(accessToken),
        commerceApi.listSubscriptions(accessToken),
        commerceApi.listAssets(accessToken),
      ]);
      setContracts(contractRows);
      setSubscriptions(subscriptionRows);
      setAssets(assetRows);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load lifecycle data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [accessToken]);

  const onUpdateSubscriptionStatus = async (subscriptionId: string, status: SubscriptionStatus) => {
    if (!accessToken) return;
    setSavingSubscriptionId(subscriptionId);
    setError('');
    try {
      const updated = await commerceApi.updateSubscriptionStatus(accessToken, subscriptionId, status);
      setSubscriptions((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update subscription status');
    } finally {
      setSavingSubscriptionId(null);
    }
  };

  return (
    <section className="content-wrap fade-in">
      <div className="content-head">
        <h1>Lifecycle</h1>
        <p className="lead">Contracts, subscriptions, and assets linked to ordered solutions.</p>
      </div>

      {loading && <div className="mini-note">Loading lifecycle data...</div>}
      {error && <div className="error-text">{error}</div>}

      <div className="table-wrap">
        <h3>Contracts</h3>
        <table className="cart-table">
          <thead>
            <tr>
              <th>Contract</th>
              <th>Order</th>
              <th>Status</th>
              <th>Term</th>
              <th>SLA</th>
              <th>Start</th>
            </tr>
          </thead>
          <tbody>
            {contracts.map((contract) => (
              <tr key={contract.id}>
                <td>{contract.id.slice(0, 8).toUpperCase()}</td>
                <td>{contract.order_id.slice(0, 8).toUpperCase()}</td>
                <td>{contract.status}</td>
                <td>{contract.term_months} months</td>
                <td>{contract.sla_tier}</td>
                <td>{contract.start_date}</td>
              </tr>
            ))}
            {contracts.length === 0 && (
              <tr>
                <td colSpan={6} className="mini-note">No contracts found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="table-wrap">
        <h3>Subscriptions</h3>
        <table className="cart-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Interval</th>
              <th>Qty</th>
              <th>Unit</th>
              <th>Status</th>
              <th>Next Billing</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {subscriptions.map((subscription) => (
              <tr key={subscription.id}>
                <td>{subscription.name}</td>
                <td>{subscription.interval}</td>
                <td>{subscription.qty}</td>
                <td>${subscription.unit_price.toFixed(2)}</td>
                <td>{subscription.status}</td>
                <td>{subscription.next_billing_date || '-'}</td>
                <td>
                  {isAdmin ? (
                    <select
                      value={subscription.status}
                      disabled={savingSubscriptionId === subscription.id}
                      onChange={(e) => onUpdateSubscriptionStatus(subscription.id, e.target.value as SubscriptionStatus)}
                    >
                      {statusOptions.map((status) => (
                        <option key={status} value={status}>
                          {status}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="mini-note">Admin only</span>
                  )}
                </td>
              </tr>
            ))}
            {subscriptions.length === 0 && (
              <tr>
                <td colSpan={7} className="mini-note">No subscriptions found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="table-wrap">
        <h3>Assets / CI Registry</h3>
        <table className="cart-table">
          <thead>
            <tr>
              <th>Asset</th>
              <th>Type</th>
              <th>Status</th>
              <th>SKU</th>
              <th>Serial</th>
              <th>Location</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((asset) => (
              <tr key={asset.id}>
                <td>{asset.name}</td>
                <td>{asset.asset_type}</td>
                <td>{asset.status}</td>
                <td>{asset.sku || '-'}</td>
                <td>{asset.serial_number || '-'}</td>
                <td>{asset.location || '-'}</td>
              </tr>
            ))}
            {assets.length === 0 && (
              <tr>
                <td colSpan={6} className="mini-note">No assets registered yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};
