import { ArrowUpRight, CalendarClock, CheckCircle2, Clock3, Package, Plus } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { BusinessIntakeModal } from '../components/BusinessIntakeModal';
import { useAuth } from '../context/AuthContext';
import type { OrderSummary } from '../types/commerce';
import { extractApiError } from '../utils/extractApiError';

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : '—');

const statusTone = (status: string): string => {
  if (['DELIVERED', 'ACTIVE'].includes(status)) return 'good';
  if (['SHIPPED', 'PROCESSING', 'SUBMITTED', 'VENDOR_ORDERED'].includes(status)) return 'progress';
  return 'muted';
};

const prettyStatus = (status: string): string =>
  status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

export const OrdersPage = () => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  // BUG-ORD-002: open the requirements intake before the builder, so a new
  // design starts from real business context instead of empty/stale data.
  const [intakeOpen, setIntakeOpen] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    commerceApi
      .listOrders(accessToken)
      .then(setOrders)
      .catch((err: any) => setError(extractApiError(err, 'Failed to load orders')))
      .finally(() => setLoading(false));
  }, [accessToken]);

  const sortedOrders = useMemo(
    () => [...orders].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at)),
    [orders],
  );

  const stats = useMemo(() => ({
    total: sortedOrders.length,
    inProgress: sortedOrders.filter((o) => ['SUBMITTED', 'PROCESSING', 'SHIPPED', 'VENDOR_ORDERED'].includes(o.status)).length,
    delivered: sortedOrders.filter((o) => ['DELIVERED', 'ACTIVE'].includes(o.status)).length,
    awaiting: sortedOrders.filter((o) => !o.confirmed_delivery_date).length,
  }), [sortedOrders]);

  return (
    <section className="content-wrap fade-in ord-page">
      <header className="apx-header">
        <div className="apx-header-text">
          <h1>Orders</h1>
          <p className="apx-subtitle">Track every order from supplier and QC through shipping and delivery.</p>
        </div>
        <button className="apx-add-btn" onClick={() => setIntakeOpen(true)}>
          <Plus size={18} /> New request
        </button>
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
          <div className="apx-stat-head"><span>Delivered</span><span className="apx-stat-icon green"><CheckCircle2 size={16} /></span></div>
          <div className="apx-stat-value">{stats.delivered}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Awaiting confirmed date</span><span className="apx-stat-icon violet"><CalendarClock size={16} /></span></div>
          <div className="apx-stat-value">{stats.awaiting}</div>
        </article>
      </div>

      <div className="apx-table-card ord-table-card">
        <div className="ord-table">
          <div className="ord-thead">
            <span>Order ID</span>
            <span>Created</span>
            <span>Status</span>
            <span>Fulfillment</span>
            <span />
          </div>

          {loading && <div className="apx-empty">Loading orders…</div>}
          {!loading && sortedOrders.length === 0 && (
            <div className="ord-empty">
              <span className="ord-empty-icon"><Package size={26} strokeWidth={1.3} /></span>
              <p>No orders yet. Convert an accepted quote or start a new design to create one.</p>
              <button className="apx-add-btn" onClick={() => setIntakeOpen(true)}>
                <Plus size={17} /> Start new request
              </button>
            </div>
          )}

          {sortedOrders.map((order) => (
            <div
              key={order.id}
              className="ord-row"
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/shop/orders/${order.id}`)}
              onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/shop/orders/${order.id}`); }}
            >
              <span className="ord-id">{order.public_id}</span>
              <span className="ord-created">{formatDateTime(order.created_at)}</span>
              <span>
                <span className={`ord-status ord-status-${statusTone(order.status)}`}>{prettyStatus(order.status)}</span>
              </span>
              <span className="ord-fulfillment">
                <span>ETA: {order.estimated_delivery_date || '—'}</span>
                <span>Confirmed: {order.confirmed_delivery_date || '—'}</span>
              </span>
              <span className="ord-row-action">
                <Link className="ord-open" to={`/shop/orders/${order.id}`} onClick={(e) => e.stopPropagation()}>
                  Open <ArrowUpRight size={15} />
                </Link>
              </span>
            </div>
          ))}
        </div>
      </div>
      <BusinessIntakeModal open={intakeOpen} onClose={() => setIntakeOpen(false)} />
    </section>
  );
};
