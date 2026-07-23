import { useEffect, useMemo, useState } from 'react';
import { Download, TrendingUp } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { Address, BillingOverview, InvoiceRecord, OnboardingProfile, PaymentRecord, SubscriptionSummary } from '../types/commerce';
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
const formatAddress = (addr?: Address): string => {
  if(!addr) return ''; //null or undefined
  return [addr.line1, addr.line2, addr.city, addr.state, addr.postal_code, addr.country]
  .filter(Boolean) //filter out empty or null strinhgs
  .join(', ');
};

const successfulPayment= (invoice: InvoiceRecord) : PaymentRecord | null => 
  invoice.payments.find((p) => p.status === 'SUCCEEDED') ?? null;

const downloadCsv = (filename: string, rows: InvoiceRecord[], profile: OnboardingProfile | null) => {
  const header = [
    'Invoice ID',
    'Customer',
    'Customer Email',
    'Billing Address',
    'Billing Period',
    'Issue Date',
    'Due Date',
    'Status',
    'Total Amount',
    'Currency',
    'Payment Method',
    'Payment Date',
    'Payment Reference',
  ];
  
  const lines = [header.join(',')].concat(
    rows.map((r) => {
      // Look up the successful payment (if any) for this specific invoice.
      const paid = successfulPayment(r);
      return [
        invoiceRef(r),                              // Invoice ID (e.g. INV-1A2B3C4D)
        profile?.organization_name ?? '',           // Customer (same for all rows in this tenant)
        profile?.admin_email ?? '',                 // Customer Email
        formatAddress(profile?.billing_address),    // Billing Address (flattened)
        periodLong(r.billing_month),                // Billing Period (e.g. "Jun 2026")
        r.issued_at,                                // Issue Date (raw ISO date)
        r.due_date,                                 // Due Date
        r.status,                                   // DUE | PAID | VOID
        r.amount.toFixed(2),                        // Total Amount, 2 decimals
        r.currency,                                 // Currency (e.g. USD)
        paid?.method ?? '',                         // How it was paid: CARD | BANK_TRANSFER | MANUAL
        r.paid_at ?? paid?.paid_at ?? '',           // When it was paid (invoice field, fall back to payment)
        paid?.external_reference ?? '',             // Gateway/txn reference, if any
      ]
        .map(csvCell) // escape commas/quotes/newlines in every cell
        .join(',');
    }),
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

  return (
    <section className="content-wrap fade-in billing-page">
      <header className="bil-header">
        <h1>Billing</h1>
        <p className="bil-subtitle">Recurring charges and invoices.</p>
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
                onClick={() => downloadCsv('invoices.csv', invoices, profile)}
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
                        onClick={() => downloadCsv(`${invoiceRef(invoice)}.csv`, [invoice], profile)}
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
