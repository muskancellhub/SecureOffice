import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Boxes, CalendarClock, Check, Layers, Package } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { VendorOrderDetail, VendorOrderLine } from '../types/commerce';
import { extractApiError } from '../utils/extractApiError';

// Vendor-facing fulfillment view. Same status ladder as the buyer order page,
// minus any pricing/payment surface.
const timelineSteps = ['Ordered', 'Supplier', 'QC', 'Shipped', 'Delivered'] as const;
const statusStepIndex: Record<string, number> = {
  SUBMITTED: 0, PROCESSING: 2, VENDOR_ORDERED: 2, SHIPPED: 3, DELIVERED: 4, ACTIVE: 4,
};

const fmtIso = (d?: string | null): string => (d ? String(d).slice(0, 10) : '—');
const prettyStatus = (s: string): string => s.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
const statusTone = (s: string): string => {
  const u = (s || '').toUpperCase();
  if (['DELIVERED', 'ACTIVE', 'COMPLETED'].includes(u)) return 'good';
  if (['SHIPPED', 'PROCESSING', 'SUBMITTED', 'VENDOR_ORDERED'].includes(u)) return 'progress';
  return 'muted';
};

export const VendorOrderDetailsPage = () => {
  const { orderId } = useParams();
  const { accessToken } = useAuth();
  const [order, setOrder] = useState<VendorOrderDetail | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!accessToken || !orderId) return;
    setError('');
    commerceApi
      .getVendorOrder(accessToken, orderId)
      .then(setOrder)
      .catch((err: any) => setError(extractApiError(err, 'Failed to load order')));
  }, [accessToken, orderId]);

  const activeStepIndex = useMemo(() => (order ? statusStepIndex[order.status] ?? 0 : 0), [order]);

  const sortedLines = useMemo(() => {
    const devices: VendorOrderLine[] = [];
    const services: VendorOrderLine[] = [];
    (order?.lines || []).forEach((line) => {
      if (line.line_type === 'SERVICE') services.push(line);
      else devices.push(line);
    });
    return [...devices, ...services];
  }, [order?.lines]);

  return (
    <section className="content-wrap fade-in odx-page">
      {error && <div className="error-text">{error}</div>}

      {order && (
        <>
          <header className="apx-header">
            <div className="apx-header-text">
              <Link to="/shop/vendor/orders" className="dnb-back"><ArrowLeft size={15} /> Back to orders</Link>
              <h1>Order {order.public_id}</h1>
              <p className="apx-subtitle">
                {order.buyer_company ? `For ${order.buyer_company}. ` : ''}Fulfillment status for the items you supply.
              </p>
              <div className="apx-scope">
                <span className={`ord-status ord-status-${statusTone(order.status)}`}>{prettyStatus(order.status)}</span>
              </div>
            </div>
          </header>

          <div className="apx-stats odx-stats">
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Your line items</span><span className="apx-stat-icon blue"><Layers size={16} /></span></div>
              <div className="apx-stat-value">{order.line_count}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Units to supply</span><span className="apx-stat-icon green"><Boxes size={16} /></span></div>
              <div className="apx-stat-value">{order.total_qty}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Est. delivery</span><span className="apx-stat-icon amber"><CalendarClock size={16} /></span></div>
              <div className="apx-stat-value apx-stat-text">{fmtIso(order.estimated_delivery_date)}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Confirmed delivery</span><span className="apx-stat-icon violet"><CalendarClock size={16} /></span></div>
              <div className="apx-stat-value apx-stat-text">{fmtIso(order.confirmed_delivery_date)}</div>
            </article>
          </div>

          {/* Fulfillment timeline */}
          <div className="apx-table-card odx-track-card">
            <div className="dnb-card-head"><h3 className="apx-modal-title" style={{ margin: 0 }}>Fulfillment</h3></div>
            <div className="dbx-track odx-track">
              {timelineSteps.map((step, index) => {
                const state = index < activeStepIndex ? 'done' : index === activeStepIndex ? 'active' : '';
                return (
                  <div key={step} className={`dbx-track-step ${state}`}>
                    <span className="dbx-track-ico">{index < activeStepIndex ? <Check size={16} /> : index + 1}</span>
                    <span className="dbx-track-lbl">{step}</span>
                    {index < timelineSteps.length - 1 && <span className="dbx-track-line" />}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Your order lines — no pricing, quantities only */}
          <div className="apx-table-card dnb-bom-card">
            <div className="dnb-card-head"><h3 className="apx-modal-title" style={{ margin: 0 }}>Your items</h3></div>
            {sortedLines.length > 0 ? (
              <table className="dnb-bom">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>SKU</th>
                    <th>Type</th>
                    <th className="dnb-num">Qty</th>
                    <th>Billing</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedLines.map((line) => (
                    <tr key={line.id}>
                      <td><div className="dnb-bom-name">{line.name}</div></td>
                      <td>{line.sku || '—'}</td>
                      <td><span className="dnb-cat-tag">{prettyStatus(line.line_type)}</span></td>
                      <td className="dnb-num">{line.qty}</td>
                      <td>
                        <span className="odx-billing">
                          {line.billing === 'RECURRING' ? `Recurring${line.interval ? ` / ${line.interval.toLowerCase()}` : ''}` : 'One-time'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="mini-note">No line items found for your products on this order.</p>
            )}
          </div>
        </>
      )}

      {!order && !error && (
        <div className="odx-loading"><Package size={26} strokeWidth={1.3} /> Loading order…</div>
      )}
    </section>
  );
};
