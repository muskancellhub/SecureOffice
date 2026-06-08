import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowUpRight, CalendarClock, Check, CreditCard, Layers, Package, RefreshCw } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { startOrderCheckout } from '../api/billingApi';
import { useAuth } from '../context/AuthContext';
import type { OrderDetail, OrderLine, WorkflowInstance } from '../types/commerce';
import { extractApiError } from '../utils/extractApiError';

const timelineSteps = ['Ordered', 'Supplier', 'QC', 'Shipped', 'Delivered'] as const;
const statusStepIndex: Record<string, number> = {
  SUBMITTED: 0, PROCESSING: 2, VENDOR_ORDERED: 2, SHIPPED: 3, DELIVERED: 4, ACTIVE: 4,
};

const money = (v: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(v || 0);
const fmtIso = (d?: string | null): string => (d ? String(d).slice(0, 10) : '—');
const prettyStatus = (s: string): string => s.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
const statusTone = (s: string): string => {
  const u = (s || '').toUpperCase();
  if (['DELIVERED', 'ACTIVE', 'COMPLETED'].includes(u)) return 'good';
  if (['SHIPPED', 'PROCESSING', 'SUBMITTED', 'VENDOR_ORDERED'].includes(u)) return 'progress';
  return 'muted';
};

export const OrderDetailsPage = () => {
  const { orderId } = useParams();
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowInstance | null>(null);
  const [error, setError] = useState('');
  const [payingWithCard, setPayingWithCard] = useState(false);

  const load = async () => {
    if (!accessToken || !orderId) return;
    setError('');
    try {
      const [orderData, workflowData] = await Promise.all([
        commerceApi.getOrder(accessToken, orderId),
        commerceApi.getOrderWorkflow(accessToken, orderId),
      ]);
      setOrder(orderData);
      setWorkflow(workflowData);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load order'));
    }
  };

  useEffect(() => { load(); }, [accessToken, orderId]);

  const onPayWithCard = async () => {
    if (!orderId) return;
    setPayingWithCard(true);
    setError('');
    try {
      const { data } = await startOrderCheckout(orderId);
      window.location.assign(data.url);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to start checkout'));
      setPayingWithCard(false);
    }
  };

  const isPayable = order?.status === 'SUBMITTED';

  const parentNameById = useMemo(() => {
    const map = new Map<string, string>();
    (order?.lines || []).forEach((line) => map.set(line.id, line.name));
    return map;
  }, [order?.lines]);

  const activeStepIndex = useMemo(() => {
    if (workflow?.steps?.length) {
      const sorted = [...workflow.steps].sort((a, b) => a.sequence - b.sequence);
      const inProgressIndex = sorted.findIndex((step) => step.status === 'IN_PROGRESS');
      if (inProgressIndex >= 0) return inProgressIndex;
      const doneCount = sorted.filter((step) => step.status === 'DONE').length;
      return Math.max(0, Math.min(sorted.length - 1, doneCount - 1));
    }
    if (!order) return 0;
    return statusStepIndex[order.status] ?? 0;
  }, [order, workflow]);

  const timelineLabels = useMemo(() => {
    if (workflow?.steps?.length) {
      return [...workflow.steps].sort((a, b) => a.sequence - b.sequence).map((step) => step.display_name);
    }
    return [...timelineSteps];
  }, [workflow]);

  const sortedLines = useMemo(() => {
    const devices: OrderLine[] = [];
    const services: OrderLine[] = [];
    (order?.lines || []).forEach((line) => {
      if (line.line_type === 'SERVICE') services.push(line);
      else devices.push(line);
    });
    return [...devices, ...services];
  }, [order?.lines]);

  const totals = useMemo(() => {
    let oneTime = 0;
    let recurring = 0;
    (order?.lines || []).forEach((line) => {
      const amt = (line.unit_price || 0) * (line.qty || 1);
      if (line.billing === 'RECURRING') recurring += amt;
      else oneTime += amt;
    });
    return { oneTime, recurring, items: (order?.lines || []).length };
  }, [order?.lines]);

  return (
    <section className="content-wrap fade-in odx-page">
      {error && <div className="error-text">{error}</div>}

      {order && (
        <>
          <header className="apx-header">
            <div className="apx-header-text">
              <Link to="/shop/orders" className="dnb-back"><ArrowLeft size={15} /> Back to orders</Link>
              <h1>Order {order.public_id}</h1>
              <p className="apx-subtitle">Track this order from supplier and QC through shipping and delivery.</p>
              <div className="apx-scope">
                <span className={`ord-status ord-status-${statusTone(order.status)}`}>{prettyStatus(order.status)}</span>
                {order.quote_public_id && (
                  <button type="button" className="dnb-meta-link" onClick={() => navigate(`/shop/orders`)}>
                    Quote {order.quote_public_id} <ArrowUpRight size={13} />
                  </button>
                )}
                {workflow && <span className="apx-scope-meta">Workflow {prettyStatus(workflow.status)}</span>}
              </div>
            </div>
            {isPayable && (
              <button className="apx-add-btn" onClick={onPayWithCard} disabled={payingWithCard}>
                <CreditCard size={18} /> {payingWithCard ? 'Redirecting…' : 'Pay with card'}
              </button>
            )}
          </header>

          <div className="apx-stats odx-stats">
            <article className="apx-stat">
              <div className="apx-stat-head"><span>One-time total</span><span className="apx-stat-icon green"><CreditCard size={16} /></span></div>
              <div className="apx-stat-value">{money(totals.oneTime)}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Recurring / mo</span><span className="apx-stat-icon violet"><RefreshCw size={16} /></span></div>
              <div className="apx-stat-value">{money(totals.recurring)}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Line items</span><span className="apx-stat-icon blue"><Layers size={16} /></span></div>
              <div className="apx-stat-value">{totals.items}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Est. delivery</span><span className="apx-stat-icon amber"><CalendarClock size={16} /></span></div>
              <div className="apx-stat-value apx-stat-text">{fmtIso(order.estimated_delivery_date)}</div>
            </article>
          </div>

          {/* Fulfillment timeline */}
          <div className="apx-table-card odx-track-card">
            <div className="dnb-card-head"><h3 className="apx-modal-title" style={{ margin: 0 }}>Fulfillment</h3></div>
            <div className="dbx-track odx-track">
              {timelineLabels.map((step, index) => {
                const state = index < activeStepIndex ? 'done' : index === activeStepIndex ? 'active' : '';
                return (
                  <div key={step} className={`dbx-track-step ${state}`}>
                    <span className="dbx-track-ico">{index < activeStepIndex ? <Check size={16} /> : index + 1}</span>
                    <span className="dbx-track-lbl">{step}</span>
                    {index < timelineLabels.length - 1 && <span className="dbx-track-line" />}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Order lines */}
          <div className="apx-table-card dnb-bom-card">
            <div className="dnb-card-head"><h3 className="apx-modal-title" style={{ margin: 0 }}>Order lines</h3></div>
            {sortedLines.length > 0 ? (
              <table className="dnb-bom">
                <thead>
                  <tr>
                    <th>Line</th>
                    <th>Type</th>
                    <th className="dnb-num">Qty</th>
                    <th className="dnb-num">Unit</th>
                    <th className="dnb-num">Total</th>
                    <th>Billing</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedLines.map((line) => (
                    <tr key={line.id}>
                      <td>
                        {line.parent_line_id ? (
                          <>
                            <div className="dnb-bom-name">↳ {line.name}</div>
                            <div className="dnb-bom-sub">attached to {parentNameById.get(line.parent_line_id) || 'device'}</div>
                          </>
                        ) : (
                          <div className="dnb-bom-name">{line.name}</div>
                        )}
                      </td>
                      <td><span className="dnb-cat-tag">{prettyStatus(line.line_type)}</span></td>
                      <td className="dnb-num">{line.qty}</td>
                      <td className="dnb-num">{money(line.unit_price)}</td>
                      <td className="dnb-num dnb-total">{money(line.unit_price * (line.qty || 1))}</td>
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
              <p className="mini-note">No order lines found.</p>
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
