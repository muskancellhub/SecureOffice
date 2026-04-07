import { ActivitySquare, ArrowRight, Boxes, CreditCard, LayoutGrid, Package, RefreshCcw, Route, Wrench } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { BillingOverview, CatalogItem, NetworkDesignSummary, OrderSummary, QuoteSummary, SubscriptionSummary } from '../types/commerce';

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value || 0);

const statusColor: Record<string, string> = {
  ACTIVE: 'dash-badge-green',
  PENDING: 'dash-badge-amber',
  COMPLETED: 'dash-badge-green',
  CANCELLED: 'dash-badge-red',
  draft: 'dash-badge-gray',
  reviewed: 'dash-badge-blue',
  submitted: 'dash-badge-amber',
  approved: 'dash-badge-green',
};

export const CustomerDashboardPage = () => {
  const { accessToken, user } = useAuth();
  const navigate = useNavigate();
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [quotes, setQuotes] = useState<QuoteSummary[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionSummary[]>([]);
  const [designs, setDesigns] = useState<NetworkDesignSummary[]>([]);
  const [billing, setBilling] = useState<BillingOverview | null>(null);
  const [managedServices, setManagedServices] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    Promise.allSettled([
      commerceApi.listQuotes(accessToken),
      commerceApi.listOrders(accessToken),
      commerceApi.listSubscriptions(accessToken),
      commerceApi.getBillingOverview(accessToken),
      commerceApi.getCatalog(accessToken, { type: 'SERVICE', sort: 'price_low' }),
      commerceApi.listNetworkDesigns(accessToken),
    ])
      .then(([quotesResult, ordersResult, subsResult, billingResult, servicesResult, designsResult]) => {
        setQuotes(quotesResult.status === 'fulfilled' ? quotesResult.value : []);
        setOrders(ordersResult.status === 'fulfilled' ? ordersResult.value : []);
        setSubscriptions(subsResult.status === 'fulfilled' ? subsResult.value : []);
        setBilling(billingResult.status === 'fulfilled' ? billingResult.value : null);
        setManagedServices(servicesResult.status === 'fulfilled' ? servicesResult.value : []);
        setDesigns(designsResult.status === 'fulfilled' ? designsResult.value : []);

        if (
          quotesResult.status === 'rejected'
          && ordersResult.status === 'rejected'
          && subsResult.status === 'rejected'
          && billingResult.status === 'rejected'
          && servicesResult.status === 'rejected'
          && designsResult.status === 'rejected'
        ) {
          setError('Failed to load dashboard data');
        }
      })
      .finally(() => setLoading(false));
  }, [accessToken]);

  const latestOrder = useMemo(
    () => [...orders].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))[0] || null,
    [orders],
  );
  const orderStatusCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const order of orders) {
      counts.set(order.status, (counts.get(order.status) || 0) + 1);
    }
    return Array.from(counts.entries());
  }, [orders]);

  const currentBill = billing?.totals?.current_monthly_recurring || 0;
  const projected12Month = billing?.totals?.projected_next_12_months || 0;
  const submittedDesigns = designs.filter((row) => row.status !== 'draft' && row.status !== 'reviewed');
  const profileName = user?.email ? user.email.split('@')[0] : 'there';

  return (
    <section className="content-wrap fade-in dash-page">
      {/* Header */}
      <div className="dash-header">
        <div>
          <h1>Welcome back, {profileName}</h1>
          <p className="lead">Overview of your billing, orders, subscriptions, and network designs.</p>
        </div>
        <button className="primary-btn dash-new-btn" onClick={() => navigate('/shop/flow-options')}>
          New Request <ArrowRight size={14} />
        </button>
      </div>

      {loading && <div className="dh-loading-bar"><div className="dh-loading-bar-inner" /></div>}
      {error && <div className="onboarding-alert error">{error}</div>}

      {/* Top KPI row */}
      <div className="dash-kpi-row">
        <div className="dash-kpi-card">
          <div className="dash-kpi-icon dash-kpi-icon-pink"><CreditCard size={18} /></div>
          <div className="dash-kpi-info">
            <span className="dash-kpi-label">Monthly Recurring</span>
            <strong className="dash-kpi-value">{formatCurrency(currentBill)}</strong>
          </div>
        </div>
        <div className="dash-kpi-card">
          <div className="dash-kpi-icon"><Package size={18} /></div>
          <div className="dash-kpi-info">
            <span className="dash-kpi-label">Total Orders</span>
            <strong className="dash-kpi-value">{orders.length}</strong>
          </div>
        </div>
        <div className="dash-kpi-card">
          <div className="dash-kpi-icon"><Boxes size={18} /></div>
          <div className="dash-kpi-info">
            <span className="dash-kpi-label">Active Subscriptions</span>
            <strong className="dash-kpi-value">{subscriptions.filter((s) => s.status === 'ACTIVE').length}</strong>
          </div>
        </div>
        <div className="dash-kpi-card">
          <div className="dash-kpi-icon"><Route size={18} /></div>
          <div className="dash-kpi-info">
            <span className="dash-kpi-label">Designs</span>
            <strong className="dash-kpi-value">{designs.length}</strong>
          </div>
        </div>
      </div>

      <div className="dash-grid">
        {/* Billing */}
        <article className="dash-card">
          <div className="dash-card-head">
            <h3><CreditCard size={15} /> Billing</h3>
            <button className="ghost-btn dash-card-action" onClick={() => navigate('/shop/billing')}>View <ArrowRight size={12} /></button>
          </div>
          <div className="dash-mini-kpis">
            <div>
              <span>Recurring</span>
              <strong>{formatCurrency(currentBill)}</strong>
            </div>
            <div>
              <span>12-month projected</span>
              <strong>{formatCurrency(projected12Month)}</strong>
            </div>
            <div>
              <span>Past invoices</span>
              <strong>{billing?.past_months?.length || 0}</strong>
            </div>
          </div>
        </article>

        {/* Last Procurement */}
        <article className="dash-card">
          <div className="dash-card-head">
            <h3><Package size={15} /> Last Procurement</h3>
            <button className="ghost-btn dash-card-action" onClick={() => latestOrder ? navigate(`/shop/orders/${latestOrder.id}`) : navigate('/shop/orders')}>
              View <ArrowRight size={12} />
            </button>
          </div>
          {latestOrder ? (
            <div className="dash-order-preview">
              <div className="dash-order-id">#{latestOrder.public_id || latestOrder.id.slice(0, 8).toUpperCase()}</div>
              <span className={`dash-badge ${statusColor[latestOrder.status] || ''}`}>{latestOrder.status}</span>
              <span className="mini-note">{new Date(latestOrder.created_at).toLocaleDateString()}</span>
            </div>
          ) : (
            <p className="mini-note">No procurement orders yet. Start a new request to get going.</p>
          )}
        </article>

        {/* Managed Services */}
        <article className="dash-card">
          <div className="dash-card-head">
            <h3><Wrench size={15} /> Managed Services</h3>
            <button className="ghost-btn dash-card-action" onClick={() => navigate('/shop/services')}>Browse <ArrowRight size={12} /></button>
          </div>
          <div className="dash-mini-kpis">
            <div>
              <span>Catalog</span>
              <strong>{managedServices.length}</strong>
            </div>
            <div>
              <span>Active</span>
              <strong>{subscriptions.filter((s) => s.status === 'ACTIVE').length}</strong>
            </div>
            <div>
              <span>Total</span>
              <strong>{subscriptions.length}</strong>
            </div>
          </div>
        </article>

        {/* Design History */}
        <article className="dash-card">
          <div className="dash-card-head">
            <h3><LayoutGrid size={15} /> Design History</h3>
            <button className="ghost-btn dash-card-action" onClick={() => navigate('/shop/designs')}>View all <ArrowRight size={12} /></button>
          </div>
          <div className="dash-mini-kpis">
            <div>
              <span>Quotes</span>
              <strong>{quotes.length}</strong>
            </div>
            <div>
              <span>Submitted</span>
              <strong>{submittedDesigns.length}</strong>
            </div>
            <div>
              <span>Latest</span>
              <strong>{designs[0]?.status || 'N/A'}</strong>
            </div>
          </div>
        </article>

        {/* Subscriptions - full width */}
        <article className="dash-card dash-card-wide">
          <div className="dash-card-head">
            <h3><Boxes size={15} /> Subscriptions</h3>
            <button className="ghost-btn dash-card-action" onClick={() => navigate('/shop/lifecycle')}>Lifecycle <ArrowRight size={12} /></button>
          </div>
          {subscriptions.length === 0 ? (
            <p className="mini-note">No subscriptions yet.</p>
          ) : (
            <div className="dash-sub-list">
              {subscriptions.slice(0, 5).map((sub) => (
                <div key={sub.id} className="dash-sub-row">
                  <span className="dash-sub-name">{sub.name}</span>
                  <span className="dash-sub-qty">x{sub.qty}</span>
                  <span className={`dash-badge ${statusColor[sub.status] || ''}`}>{sub.status}</span>
                </div>
              ))}
            </div>
          )}
        </article>

        {/* Order Status */}
        <article className="dash-card dash-card-wide">
          <div className="dash-card-head">
            <h3><ActivitySquare size={15} /> Order Status</h3>
            <button className="ghost-btn dash-card-action" onClick={() => navigate('/shop/orders')}>All orders <ArrowRight size={12} /></button>
          </div>
          {orderStatusCounts.length === 0 ? (
            <p className="mini-note">No orders yet. Create a new request to start procurement.</p>
          ) : (
            <div className="dash-status-chips">
              {orderStatusCounts.map(([status, count]) => (
                <div key={status} className="dash-status-chip">
                  <span className="dash-status-count">{count}</span>
                  <span className="dash-status-label">{status}</span>
                </div>
              ))}
            </div>
          )}
        </article>

        {/* Recent Designs */}
        <article className="dash-card dash-card-wide">
          <div className="dash-card-head">
            <h3><RefreshCcw size={15} /> Recent Designs</h3>
            <button className="ghost-btn dash-card-action" onClick={() => navigate('/shop/designs/new')}>New design <ArrowRight size={12} /></button>
          </div>
          {designs.length === 0 ? (
            <p className="mini-note">No design snapshots yet. Create one from New Request.</p>
          ) : (
            <div className="dash-designs-list">
              {designs.slice(0, 4).map((design) => (
                <Link key={design.id} to={`/shop/designs/${design.id}`} className="dash-design-row">
                  <span className="dash-design-name">{design.designName || design.id.slice(0, 8)}</span>
                  <span className={`dash-badge ${statusColor[design.status] || ''}`}>{design.status}</span>
                  <span className="dash-design-capex">{formatCurrency(design.estimatedCapex)}</span>
                </Link>
              ))}
            </div>
          )}
        </article>
      </div>
    </section>
  );
};
