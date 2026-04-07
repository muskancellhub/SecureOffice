import { ArrowUpRight, Clock3, PackageCheck, PackageSearch } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { OrderSummary } from '../types/commerce';

const statusSteps = ['Ordered', 'Supplier', 'QC', 'Shipped', 'Delivered'] as const;
const statusStepIndex: Record<string, number> = {
  SUBMITTED: 0,
  PROCESSING: 2,
  VENDOR_ORDERED: 2,
  SHIPPED: 3,
  DELIVERED: 4,
  ACTIVE: 4,
};

export const OrdersPage = () => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!accessToken) return;
    commerceApi
      .listOrders(accessToken)
      .then(setOrders)
      .catch((err: any) => setError(err?.response?.data?.detail || 'Failed to load orders'));
  }, [accessToken]);

  const sortedOrders = useMemo(
    () => [...orders].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at)),
    [orders],
  );
  const featuredOrder = useMemo(() => sortedOrders[0] || null, [sortedOrders]);
  const activeStepIndex = useMemo(() => {
    if (!featuredOrder) return 2;
    return statusStepIndex[featuredOrder.status] ?? 2;
  }, [featuredOrder]);
  const inProgressCount = useMemo(
    () => sortedOrders.filter((order) => ['SUBMITTED', 'PROCESSING', 'SHIPPED'].includes(order.status)).length,
    [sortedOrders],
  );
  const deliveredCount = useMemo(
    () => sortedOrders.filter((order) => ['DELIVERED', 'ACTIVE'].includes(order.status)).length,
    [sortedOrders],
  );
  const awaitingConfirmedCount = useMemo(
    () => sortedOrders.filter((order) => !order.confirmed_delivery_date).length,
    [sortedOrders],
  );

  const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : '-');
  const statusTone = (status: string) => {
    if (['DELIVERED', 'ACTIVE'].includes(status)) return 'is-good';
    if (['SHIPPED', 'PROCESSING', 'SUBMITTED'].includes(status)) return 'is-progress';
    return 'is-muted';
  };

  return (
    <section className="content-wrap fade-in orders-page">
      <div className="content-head row-between orders-hero">
        <div>
          <p className="orders-eyebrow">Operations</p>
          <h1>Order Tracker</h1>
          <p className="lead">Track supplier, QC, shipping, and delivery milestones from one enterprise view.</p>
        </div>
        <button className="primary-btn" onClick={() => navigate('/shop/flow-options')}>
          New Request
        </button>
      </div>

      {error && <div className="error-text">{error}</div>}

      <section className="orders-overview-grid">
        <article className="order-status-card orders-feature-card">
          <div className="orders-feature-top row-between">
            <div>
              <div className="orders-id-row">
                <PackageSearch size={17} />
                <h3>Order #{featuredOrder ? featuredOrder.public_id : 'No Orders Yet'}</h3>
              </div>
              <div className="orders-meta-row">
                <span className="orders-meta-pill">
                  <Clock3 size={13} />
                  Created {featuredOrder ? formatDateTime(featuredOrder.created_at) : '-'}
                </span>
                <span className="orders-meta-pill">
                  ETA {featuredOrder?.estimated_delivery_date || 'TBD'}
                </span>
                <span className="orders-meta-pill">
                  Confirmed {featuredOrder?.confirmed_delivery_date || 'Pending'}
                </span>
              </div>
            </div>
            <span className={`badge orders-status-badge ${statusTone(featuredOrder?.status || 'PROCESSING')}`}>
              {featuredOrder?.status || 'PROCESSING'}
            </span>
          </div>
          <div className="status-track orders-status-track">
            {statusSteps.map((step, index) => {
              const stateClass = index < activeStepIndex ? 'done' : index === activeStepIndex ? 'active' : '';
              return (
                <div key={step} className={`track-step ${stateClass}`}>
                  <span className="dot" />
                  <span>{step.replace('_', ' ')}</span>
                </div>
              );
            })}
          </div>
        </article>

        <aside className="orders-kpi-panel">
          <div className="orders-kpi-card">
            <span>Total orders</span>
            <strong>{sortedOrders.length}</strong>
          </div>
          <div className="orders-kpi-card">
            <span>In progress</span>
            <strong>{inProgressCount}</strong>
          </div>
          <div className="orders-kpi-card">
            <span>Delivered</span>
            <strong>{deliveredCount}</strong>
          </div>
          <div className="orders-kpi-card">
            <span>Awaiting confirmed date</span>
            <strong>{awaitingConfirmedCount}</strong>
          </div>
        </aside>
      </section>

      <section className="orders-list-card">
        <div className="row-between orders-list-head">
          <h3>All Orders</h3>
          <span className="mini-note">Click any order to view line-level workflow.</span>
        </div>

        <div className="table-wrap orders-table-wrap">
          <table className="cart-table orders-table">
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Created</th>
                <th>Status</th>
                <th>Fulfillment</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {sortedOrders.map((order) => (
                <tr key={order.id}>
                  <td>
                    <strong>{order.public_id}</strong>
                  </td>
                  <td>{formatDateTime(order.created_at)}</td>
                  <td>
                    <span className={`badge orders-status-badge ${statusTone(order.status)}`}>{order.status}</span>
                  </td>
                  <td className="orders-fulfillment-cell">
                    <span>ETA: {order.estimated_delivery_date || '-'}</span>
                    <span>Confirmed: {order.confirmed_delivery_date || '-'}</span>
                  </td>
                  <td>
                    <Link className="ghost-link orders-open-link" to={`/shop/orders/${order.id}`}>
                      Open <ArrowUpRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
              {sortedOrders.length === 0 && (
                <tr>
                  <td colSpan={5} className="mini-note">
                    No orders yet. Convert an accepted quote to create one.
                    {' '}
                    <button className="secondary-btn" onClick={() => navigate('/shop/flow-options')}>
                      Start new request
                    </button>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
};
