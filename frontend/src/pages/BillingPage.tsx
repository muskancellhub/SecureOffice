import { useEffect, useMemo, useState } from 'react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { BillingOverview, InvoiceRecord } from '../types/commerce';

export const BillingPage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [runningInvoicing, setRunningInvoicing] = useState(false);
  const [payingInvoiceId, setPayingInvoiceId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    try {
      const [overviewData, invoiceRows] = await Promise.all([
        commerceApi.getBillingOverview(accessToken, { months_back: 12, months_forward: 12 }),
        commerceApi.listInvoices(accessToken),
      ]);
      setOverview(overviewData);
      setInvoices(invoiceRows);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load billing data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [accessToken]);

  const dueInvoices = useMemo(() => invoices.filter((invoice) => invoice.status === 'DUE'), [invoices]);

  const onRunInvoicing = async () => {
    if (!accessToken) return;
    setRunningInvoicing(true);
    setError('');
    try {
      await commerceApi.runInvoicing(accessToken);
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to run invoicing');
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
      setError(err?.response?.data?.detail || 'Failed to record payment');
    } finally {
      setPayingInvoiceId(null);
    }
  };

  return (
    <section className="content-wrap fade-in">
      <div className="content-head row-between">
        <div>
          <h1>Billing</h1>
          <p className="lead">Last 12 months actuals, next 12 months projection, invoices, and payments.</p>
        </div>
        {isAdmin && (
          <button className="primary-btn" onClick={onRunInvoicing} disabled={runningInvoicing}>
            {runningInvoicing ? 'Running...' : 'Run Invoicing'}
          </button>
        )}
      </div>

      {loading && <div className="mini-note">Loading billing data...</div>}
      {error && <div className="error-text">{error}</div>}

      {overview && (
        <>
          <div className="table-wrap">
            <table className="cart-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>One-time purchases (last 12 months)</td>
                  <td>${overview.totals.one_time_last_12_months.toFixed(2)}</td>
                </tr>
                <tr>
                  <td>Recurring charges (last 12 months)</td>
                  <td>${overview.totals.recurring_last_12_months.toFixed(2)}</td>
                </tr>
                <tr>
                  <td>Current monthly recurring</td>
                  <td>${overview.totals.current_monthly_recurring.toFixed(2)}</td>
                </tr>
                <tr>
                  <td>Projected next 12 months</td>
                  <td>${overview.totals.projected_next_12_months.toFixed(2)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="table-wrap">
            <h3>Last 12 Months</h3>
            <table className="cart-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th>One-time</th>
                  <th>Recurring</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {overview.past_months.map((month) => (
                  <tr key={month.month}>
                    <td>{month.month}</td>
                    <td>${month.one_time_total.toFixed(2)}</td>
                    <td>${month.recurring_total.toFixed(2)}</td>
                    <td>${month.total.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="table-wrap">
            <h3>Projected Next 12 Months</h3>
            <table className="cart-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Recurring</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {overview.projected_months.map((month) => (
                  <tr key={month.month}>
                    <td>{month.month}</td>
                    <td>${month.recurring_total.toFixed(2)}</td>
                    <td>${month.total.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="table-wrap">
        <h3>Invoices</h3>
        <table className="cart-table">
          <thead>
            <tr>
              <th>Invoice</th>
              <th>Billing Month</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Due</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {invoices.map((invoice) => (
              <tr key={invoice.id}>
                <td>{invoice.id.slice(0, 8).toUpperCase()}</td>
                <td>{invoice.billing_month}</td>
                <td>${invoice.amount.toFixed(2)}</td>
                <td>{invoice.status}</td>
                <td>{invoice.due_date}</td>
                <td>
                  {invoice.status === 'DUE' && isAdmin ? (
                    <button className="secondary-btn" onClick={() => onMarkPaid(invoice)} disabled={payingInvoiceId === invoice.id}>
                      {payingInvoiceId === invoice.id ? 'Saving...' : 'Mark Paid'}
                    </button>
                  ) : (
                    <span className="mini-note">{invoice.payments.length} payment(s)</span>
                  )}
                </td>
              </tr>
            ))}
            {invoices.length === 0 && (
              <tr>
                <td colSpan={6} className="mini-note">No invoices found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {dueInvoices.length > 0 && <div className="mini-note">{dueInvoices.length} invoice(s) currently due.</div>}
    </section>
  );
};
