import { ArrowUpRight, Boxes, CheckCircle2, Clock3, Package, Truck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { VendorOrderSummary } from '../types/commerce';
import { extractApiError } from '../utils/extractApiError';

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : '—');

const statusTone = (status: string): string => {
  if (['DELIVERED', 'ACTIVE'].includes(status)) return 'good';
  if (['SHIPPED', 'PROCESSING', 'SUBMITTED', 'VENDOR_ORDERED'].includes(status)) return 'progress';
  return 'muted';
};

const prettyStatus = (status: string): string =>
  status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

export const VendorDashboardPage = () => {
  const { accessToken, user } = useAuth();
  const navigate = useNavigate();
  const [orders, setOrders] = useState<VendorOrderSummary[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    commerceApi
      .listVendorOrders(accessToken)
      .then(setOrders)
      .catch((err: any) => setError(extractApiError(err, 'Failed to load vendor orders')))
      .finally(() => setLoading(false));
  }, [accessToken]);

  const sortedOrders = useMemo(
    () => [...orders].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at)),
    [orders],
  );

  const stats = useMemo(() => ({
    total: sortedOrders.length,
    inProgress: sortedOrders.filter((o) => ['SUBMITTED', 'PROCESSING', 'VENDOR_ORDERED'].includes(o.status)).length,
    shipped: sortedOrders.filter((o) => o.status === 'SHIPPED').length,
    delivered: sortedOrders.filter((o) => ['DELIVERED', 'ACTIVE'].includes(o.status)).length,
    units: sortedOrders.reduce((sum, o) => sum + (o.total_qty || 0), 0),
  }), [sortedOrders]);

  const vendorName = user?.email ? user.email.split('@')[0] : 'vendor';

  return (
    <section className="content-wrap fade-in ord-page">
      <header className="apx-header">
        <div className="apx-header-text">
          <h1>Vendor orders</h1>
          <p className="apx-subtitle">
            Every order that includes your products — with fulfillment status and the quantities you need to supply.
          </p>
        </div>
      </header>

      {error && <div className="error-text">{error}</div>}

      <div className="apx-stats">
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Total orders</span><span className="apx-stat-icon blue"><Package size={16} /></span></div>
          <div className="apx-stat-value">{stats.total}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>In progress</span><span className="apx-stat-icon amber"><Clock3 size={16} /></span></div>
          <div className="apx-stat-value">{stats.inProgress}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Shipped</span><span className="apx-stat-icon violet"><Truck size={16} /></span></div>
          <div className="apx-stat-value">{stats.shipped}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Units ordered</span><span className="apx-stat-icon green"><Boxes size={16} /></span></div>
          <div className="apx-stat-value">{stats.units}</div>
        </article>
      </div>

      <div className="apx-table-card ord-table-card">
        <div className="ord-table">
          <div className="ord-thead">
            <span>Order ID</span>
            <span>Buyer</span>
            <span>Created</span>
            <span>Status</span>
            <span>Your items</span>
            <span />
          </div>

          {loading && <div className="apx-empty">Loading orders…</div>}
          {!loading && sortedOrders.length === 0 && (
            <div className="ord-empty">
              <span className="ord-empty-icon"><Package size={26} strokeWidth={1.3} /></span>
              <p>No orders yet. Orders that include your products will appear here as buyers place them.</p>
            </div>
          )}

          {sortedOrders.map((order) => (
            <div
              key={order.id}
              className="ord-row"
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/shop/vendor/orders/${order.id}`)}
              onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/shop/vendor/orders/${order.id}`); }}
            >
              <span className="ord-id">{order.public_id}</span>
              <span className="ord-created">{order.buyer_company || '—'}</span>
              <span className="ord-created">{formatDateTime(order.created_at)}</span>
              <span>
                <span className={`ord-status ord-status-${statusTone(order.status)}`}>{prettyStatus(order.status)}</span>
              </span>
              <span className="ord-fulfillment">
                <span>{order.line_count} line{order.line_count === 1 ? '' : 's'}</span>
                <span>{order.total_qty} unit{order.total_qty === 1 ? '' : 's'}</span>
              </span>
              <span className="ord-row-action">
                <Link className="ord-open" to={`/shop/vendor/orders/${order.id}`} onClick={(e) => e.stopPropagation()}>
                  Open <ArrowUpRight size={15} />
                </Link>
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
