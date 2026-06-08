import { useEffect, useMemo, useState } from 'react';
import { CreditCard, Download, Pencil, TrendingUp } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import { startSubscriptionCheckout } from '../api/billingApi';
import { useAuth } from '../context/AuthContext';
import type { BillingOverview, InvoiceRecord, OnboardingProfile, SubscriptionSummary } from '../types/commerce';
import { extractApiError } from '../utils/extractApiError';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const money = (value: number, cents = false): string =>
  '$' + new Intl.NumberFormat('en-US', {
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: cents ? 2 : 0,
  }).format(value || 0);

// "2025-07" → "Jul '25"
const monthShort = (ym: string): string => {
  const [y, m] = String(ym).split('-').map(Number);
  if (!y || !m) return ym;
  return `${MONTHS[m - 1]} '${String(y).slice(2)}`;
};

// "2026-06-01" → "Jun 2026"
const periodLong = (dateStr: string): string => {
  const [y, m] = String(dateStr).split('-').map(Number);
  if (!y || !m) return dateStr;
  return `${MONTHS[m - 1]} ${y}`;
};

const invoiceRef = (invoice: InvoiceRecord): string => `INV-${invoice.id.slice(0, 8).toUpperCase()}`;

const csvCell = (value: string | number): string => {
  const str = String(value ?? '');
  return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
};

const downloadCsv = (filename: string, rows: InvoiceRecord[]) => {
  const header = ['Invoice', 'Period', 'Status', 'Amount', 'Due date'];
  const lines = [header.join(',')].concat(
    rows.map((r) => [invoiceRef(r), periodLong(r.billing_month), r.status, r.amount.toFixed(2), r.due_date]
      .map(csvCell).join(',')),
  );
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

export const BillingPage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionSummary[]>([]);
  const [profile, setProfile] = useState<OnboardingProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [runningInvoicing, setRunningInvoicing] = useState(false);
  const [payingInvoiceId, setPayingInvoiceId] = useState<string | null>(null);
  const [subscribing, setSubscribing] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    try {
      const [overviewData, invoiceRows, subRows, profileData] = await Promise.all([
        commerceApi.getBillingOverview(accessToken, { months_back: 12, months_forward: 12 }),
        commerceApi.listInvoices(accessToken),
        commerceApi.listSubscriptions(accessToken).catch(() => [] as SubscriptionSummary[]),
        commerceApi.getOnboardingProfile(accessToken).catch(() => null),
      ]);
      setOverview(overviewData);
      setInvoices(invoiceRows);
      setSubscriptions(subRows);
      setProfile(profileData);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load billing data'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [accessToken]);

  const activeSubscriptions = useMemo(
    () => subscriptions.filter((s) => s.status === 'ACTIVE'),
    [subscriptions],
  );

  // Bars come straight from the real past-12-months series.
  const bars = useMemo(() => {
    const months = overview?.past_months ?? [];
    const max = Math.max(1, ...months.map((m) => m.total));
    return months.map((m, idx) => ({
      key: m.month,
      label: monthShort(m.month),
      heightPct: Math.max(6, Math.round((m.total / max) * 100)),
      current: idx === months.length - 1,
    }));
  }, [overview]);

  // Month-over-month recurring growth, derived from real data.
  const growthPct = useMemo(() => {
    const months = overview?.past_months ?? [];
    if (months.length < 2) return null;
    const prev = months[months.length - 2].recurring_total;
    const curr = months[months.length - 1].recurring_total;
    if (!prev) return null;
    return Math.round(((curr - prev) / prev) * 100);
  }, [overview]);

  const onRunInvoicing = async () => {
    if (!accessToken) return;
    setRunningInvoicing(true);
    setError('');
    try {
      await commerceApi.runInvoicing(accessToken);
      await load();
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to run invoicing'));
    } finally {
      setRunningInvoicing(false);
    }
  };

  const onSubscribe = async () => {
    const priceId = import.meta.env.VITE_STRIPE_DEFAULT_PRICE_ID;
    if (!priceId) {
      setError('Stripe Price ID not configured');
      return;
    }
    setSubscribing(true);
    setError('');
    try {
      const { data } = await startSubscriptionCheckout(priceId);
      window.location.assign(data.url);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to start checkout'));
      setSubscribing(false);
    }
  };

  const onMarkPaid = async (invoice: InvoiceRecord) => {
    if (!accessToken) return;
    setPayingInvoiceId(invoice.id);
    setError('');
    try {
      await commerceApi.recordInvoicePayment(accessToken, invoice.id, { amount: invoice.amount, method: 'MANUAL' });
      await load();
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to record payment'));
    } finally {
      setPayingInvoiceId(null);
    }
  };

  const mrr = overview?.totals.current_monthly_recurring ?? 0;
  const projected = overview?.totals.projected_next_12_months ?? 0;
  const cardLast4 = profile?.payment_method_last4 ?? null;
  const cardBrand = profile?.payment_method_type === 'BANK_TRANSFER' ? 'Bank' : 'Card';
  const orgName = profile?.organization_name || 'Your organization';

  return (
    <section className="content-wrap fade-in billing-page">
      <header className="bil-header">
        <h1>Billing</h1>
        <p className="bil-subtitle">Recurring charges, invoices, and payment methods.</p>
      </header>

      {loading && <div className="mini-note">Loading billing data...</div>}
      {error && <div className="error-text">{error}</div>}

      <div className="bil-grid">
        {/* Monthly recurring revenue */}
        <article className="bil-card bil-mrr-card">
          <div className="bil-card-head">
            <span className="bil-card-label">Monthly recurring revenue</span>
            {growthPct != null && (
              <span className={`bil-growth ${growthPct >= 0 ? 'up' : 'down'}`}>
                <TrendingUp size={14} /> {growthPct >= 0 ? '+' : ''}{growthPct}%
              </span>
            )}
          </div>
          <div className="bil-mrr-value">{money(mrr)}</div>
          <div className="bil-mrr-projected">{money(projected)} projected over next 12 months</div>

          <div className="bil-chart">
            {bars.map((bar) => (
              <span
                key={bar.key}
                className={`bil-bar ${bar.current ? 'current' : ''}`}
                style={{ height: `${bar.heightPct}%` }}
                title={`${bar.label}`}
              />
            ))}
          </div>
          {bars.length > 0 && (
            <div className="bil-chart-axis">
              <span>{bars[0].label}</span>
              <span>{bars[bars.length - 1].label}</span>
            </div>
          )}
        </article>

        {/* Payment method */}
        <article className="bil-card bil-payment-card">
          <h3 className="bil-card-title">Payment method</h3>
          <div className="bil-credit-card">
            <div className="bil-cc-top">
              <span className="bil-cc-chip"><CreditCard size={20} /></span>
              <span className="bil-cc-brand">{cardBrand}</span>
            </div>
            <div className="bil-cc-number">
              <span>••••</span><span>••••</span><span>••••</span><span>{cardLast4 || '••••'}</span>
            </div>
            <div className="bil-cc-foot">
              <span>{orgName}</span>
              <span>{cardLast4 ? 'On file' : 'No card'}</span>
            </div>
          </div>
          <button className="bil-update-btn" onClick={onSubscribe} disabled={subscribing}>
            <Pencil size={15} /> {subscribing ? 'Redirecting…' : cardLast4 ? 'Update card' : 'Add a card'}
          </button>
        </article>

        {/* Active subscriptions */}
        <article className="bil-card bil-subs-card">
          <div className="bil-card-head">
            <h3 className="bil-card-title">Active subscriptions</h3>
            <span className="bil-card-meta">{activeSubscriptions.length} active</span>
          </div>
          {activeSubscriptions.length === 0 ? (
            <p className="mini-note">No active subscriptions.</p>
          ) : (
            <ul className="bil-subs-list">
              {activeSubscriptions.map((sub) => (
                <li key={sub.id} className="bil-subs-row">
                  <span className="bil-subs-name">{sub.name}</span>
                  <span className="bil-subs-qty">×{sub.qty}</span>
                  <span className="bil-subs-price">
                    {money(sub.unit_price * sub.qty, true)}/{sub.interval === 'YEAR' ? 'yr' : 'mo'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </article>

        {/* Invoice history */}
        <article className="bil-card bil-invoices-card">
          <div className="bil-card-head">
            <h3 className="bil-card-title">Invoice history</h3>
            <div className="bil-invoices-actions">
              {isAdmin && (
                <button className="bil-link-btn" onClick={onRunInvoicing} disabled={runningInvoicing}>
                  {runningInvoicing ? 'Running…' : 'Run invoicing'}
                </button>
              )}
              <button
                className="bil-link-btn"
                onClick={() => downloadCsv('invoices.csv', invoices)}
                disabled={invoices.length === 0}
              >
                Export all
              </button>
            </div>
          </div>

          {invoices.length === 0 ? (
            <p className="mini-note">No invoices found.</p>
          ) : (
            <div className="bil-invoice-table">
              <div className="bil-invoice-thead">
                <span>Invoice</span>
                <span>Period</span>
                <span>Status</span>
                <span>Amount</span>
                <span />
              </div>
              {invoices.map((invoice) => (
                <div key={invoice.id} className="bil-invoice-row">
                  <span className="bil-invoice-ref">{invoiceRef(invoice)}</span>
                  <span className="bil-invoice-period">{periodLong(invoice.billing_month)}</span>
                  <span>
                    <span className={`bil-status bil-status-${invoice.status.toLowerCase()}`}>{invoice.status}</span>
                  </span>
                  <span className="bil-invoice-amount">{money(invoice.amount, true)}</span>
                  <span className="bil-invoice-action">
                    {invoice.status === 'DUE' && isAdmin ? (
                      <button
                        className="bil-link-btn"
                        onClick={() => onMarkPaid(invoice)}
                        disabled={payingInvoiceId === invoice.id}
                      >
                        {payingInvoiceId === invoice.id ? 'Saving…' : 'Mark paid'}
                      </button>
                    ) : (
                      <button
                        className="bil-download-btn"
                        title="Download invoice (CSV)"
                        aria-label="Download invoice"
                        onClick={() => downloadCsv(`${invoiceRef(invoice)}.csv`, [invoice])}
                      >
                        <Download size={16} />
                      </button>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </article>
      </div>
    </section>
  );
};
