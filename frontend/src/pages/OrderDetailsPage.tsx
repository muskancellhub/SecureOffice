import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowUpRight, CalendarClock, Check, CheckCircle2, CreditCard, Layers, Package, RefreshCw } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { SquarePaymentForm } from '../components/SquarePaymentForm';
import type { SquarePaymentResult } from '../api/billingApi';
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
  const [showSquareForm, setShowSquareForm] = useState(false);
  const [paymentResult, setPaymentResult] = useState<SquarePaymentResult | null>(null);
  const [taxQuote, setTaxQuote] = useState<commerceApi.OrderTaxQuote | null>(null);

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
      if (!orderData.is_paid && orderData.status === 'SUBMITTED') {
        try {
          setTaxQuote(await commerceApi.getOrderTaxQuote(accessToken, orderId));
        } catch {
          setTaxQuote(null);
        }
      }
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load order'));
    }
  };

  useEffect(() => { load(); }, [accessToken, orderId]);

  const onPayWithCard = () => {
    if (!orderId) return;
    setError('');
    // Keep the buyer on-page with the embedded Square widget.
    setShowSquareForm(true);
  };

  const onSquareSuccess = async (result: SquarePaymentResult) => {
    setShowSquareForm(false);
    setPaymentResult(result);
    await load();
  };

  const isPaid = !!order?.is_paid;
  const taxUnavailable = !!taxQuote && !taxQuote.tax_available;
  const isPayable = order?.status === 'SUBMITTED' && !isPaid;

  // Card charge covers ONE-TIME lines only; recurring services are invoiced
  // monthly by the billing engine (matches the backend SquareService).
  const payTotal = useMemo(() => {
    return (order?.lines || [])
      .filter((line) => line.billing !== 'RECURRING')
      .reduce((sum, line) => sum + (line.unit_price || 0) * (line.qty || 1), 0);
  }, [order?.lines]);

  // Card charge = subtotal + sales tax (tax comes from the backend quote; JS never
  // recomputes tax). Falls back to subtotal until the quote resolves.
  const chargeTotal = taxQuote?.total ?? payTotal;

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

      {showSquareForm && orderId && (
        <SquarePaymentForm
          orderId={orderId}
          amountLabel={money(chargeTotal)}
          onSuccess={onSquareSuccess}
          onCancel={() => setShowSquareForm(false)}
        />
      )}

      {paymentResult && (
        <div className="sqpay-backdrop" onClick={() => setPaymentResult(null)}>
          <div className="sqpay-shell sqpay-success" onClick={(e) => e.stopPropagation()}>
            <div className="sqpay-success-icon"><CheckCircle2 size={48} strokeWidth={2} /></div>
            <h3 className="sqpay-title">Payment successful</h3>
            <p className="sqpay-success-sub">
              {order ? <>Order <strong>{order.public_id}</strong> is confirmed and now being processed.</>
                     : 'Your payment has been received.'}
            </p>
            <div className="sqpay-receipt">
              <div className="sqpay-receipt-row">
                <span>Amount paid</span>
                <span>{money(paymentResult.amount ?? payTotal)}</span>
              </div>
              {paymentResult.payment_id && (
                <div className="sqpay-receipt-row">
                  <span>Reference</span>
                  <span className="sqpay-receipt-ref">{paymentResult.payment_id.slice(0, 16)}</span>
                </div>
              )}
            </div>
            <div className="sqpay-actions">
              <button className="sqpay-cancel-btn" onClick={() => navigate('/shop/orders')}>
                View all orders
              </button>
              <button className="sqpay-pay-btn" onClick={() => setPaymentResult(null)}>
                Track this order
              </button>
            </div>
          </div>
        </div>
      )}

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
              <div className="odx-pay-box">
                <div className="odx-pay-line"><span>Subtotal</span><span>{money(taxQuote?.subtotal ?? payTotal)}</span></div>
                <div className="odx-pay-line">
                  <span>Sales tax</span>
                  <span>{taxQuote?.tax_available ? money(taxQuote?.tax ?? 0) : '—'}</span>
                </div>
                <div className="odx-pay-line odx-pay-total"><span>Total</span><span>{money(chargeTotal)}</span></div>
                {taxUnavailable && <p className="mini-note error-text">{taxQuote?.message || 'Tax could not be calculated right now.'}</p>}
                <button className="apx-add-btn" onClick={onPayWithCard} disabled={showSquareForm || taxUnavailable}>
                  <CreditCard size={18} /> Pay with card
                </button>
              </div>
            )}
            {isPaid && (
              <span className="odx-paid-badge" title={order?.paid_at ? `Paid ${fmtIso(order.paid_at)}` : 'Paid'}>
                <CheckCircle2 size={16} /> Paid
              </span>
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
