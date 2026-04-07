import { Fragment, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { OnboardingProfile, QuoteDetail, QuoteLine } from '../types/commerce';

const lineName = (line: QuoteLine) => line.name || line.name_snapshot || 'Line item';
const lineUnit = (line: QuoteLine) => line.final_unit_price_snapshot ?? line.unit_price;
const lineListPrice = (line: QuoteLine) => line.list_price_snapshot ?? lineUnit(line);

export const QuoteDetailsPage = () => {
  const { quoteId } = useParams();
  const { accessToken, user } = useAuth();
  const navigate = useNavigate();
  const permissionSet = useMemo(() => new Set(user?.effective_permissions || []), [user?.effective_permissions]);
  const canManagePricing = permissionSet.has('manage_pricing');
  const canSendQuote = permissionSet.has('send_quotes');
  const canConvertQuote = permissionSet.has('convert_quotes');
  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [onboarding, setOnboarding] = useState<OnboardingProfile | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sending, setSending] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [savingDefault, setSavingDefault] = useState(false);
  const [savingDeal, setSavingDeal] = useState(false);
  const [defaultDiscountInput, setDefaultDiscountInput] = useState('30');
  const [incrementalDiscountInput, setIncrementalDiscountInput] = useState('0');

  const loadQuote = async () => {
    if (!accessToken || !quoteId) return;
    setError('');
    try {
      const data = await commerceApi.getQuote(accessToken, quoteId);
      setQuote(data);
      try {
        const onboardingData = await commerceApi.getOnboardingProfile(accessToken);
        setOnboarding(onboardingData);
      } catch {
        setOnboarding(null);
      }
      setDefaultDiscountInput(((data.default_discount_pct || 0) * 100).toFixed(2));
      setIncrementalDiscountInput(((data.incremental_discount_pct || 0) * 100).toFixed(2));
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load quote');
    }
  };

  useEffect(() => {
    loadQuote();
  }, [accessToken, quoteId]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const lineById = useMemo(() => {
    const map = new Map<string, QuoteLine>();
    (quote?.lines || []).forEach((line) => map.set(line.id, line));
    return map;
  }, [quote?.lines]);

  const deviceLines = useMemo(
    () => (quote?.lines || []).filter((line) => line.line_type === 'DEVICE'),
    [quote?.lines],
  );

  const serviceLinesByParent = useMemo(() => {
    const map = new Map<string, QuoteLine[]>();
    (quote?.lines || []).forEach((line) => {
      if (line.line_type !== 'SERVICE' || !line.parent_line_id) return;
      if (!map.has(line.parent_line_id)) map.set(line.parent_line_id, []);
      map.get(line.parent_line_id)!.push(line);
    });
    return map;
  }, [quote?.lines]);

  const orphanServices = useMemo(
    () => (quote?.lines || []).filter((line) => line.line_type === 'SERVICE' && !line.parent_line_id),
    [quote?.lines],
  );
  const serviceLines = useMemo(
    () => (quote?.lines || []).filter((line) => line.line_type === 'SERVICE'),
    [quote?.lines],
  );

  const estimatedTax = useMemo(() => (quote ? quote.one_time_total * 0.08 : 0), [quote]);
  const estimatedShipping = useMemo(() => (deviceLines.length > 0 ? 49 : 0), [deviceLines.length]);
  const estimatedDueToday = useMemo(
    () => (quote ? quote.one_time_total + estimatedTax + estimatedShipping : 0),
    [quote, estimatedTax, estimatedShipping],
  );

  const onSendQuote = async () => {
    if (!accessToken || !quote) return;
    setSending(true);
    setError('');
    try {
      const updated = await commerceApi.sendQuote(accessToken, quote.id);
      setQuote(updated);
      setNotice('Quote marked as SENT.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to send quote');
    } finally {
      setSending(false);
    }
  };

  const onAcceptQuote = async () => {
    if (!accessToken || !quote) return;
    setAccepting(true);
    setError('');
    try {
      const updated = await commerceApi.acceptQuote(accessToken, quote.id);
      setQuote(updated);
      setNotice('Quote accepted and ready for conversion.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to accept quote');
    } finally {
      setAccepting(false);
    }
  };

  const onApplyDefaultDiscount = async () => {
    if (!accessToken || !quote || !canManagePricing) return;
    const pct = Number(defaultDiscountInput);
    if (!Number.isFinite(pct) || pct < 0 || pct > 95) {
      setError('Default discount must be between 0 and 95');
      return;
    }
    setSavingDefault(true);
    setError('');
    try {
      await commerceApi.updateCustomerPricing(accessToken, { default_discount_pct: pct / 100 });
      await loadQuote();
      setNotice('Default customer discount updated.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update default discount');
    } finally {
      setSavingDefault(false);
    }
  };

  const onApplyDealDiscount = async () => {
    if (!accessToken || !quote || !canManagePricing) return;
    const pct = Number(incrementalDiscountInput);
    if (!Number.isFinite(pct) || pct < 0 || pct > 95) {
      setError('Incremental deal discount must be between 0 and 95');
      return;
    }
    setSavingDeal(true);
    setError('');
    try {
      await commerceApi.updateDealPricing(accessToken, quote.id, { incremental_discount_pct: pct / 100 });
      await loadQuote();
      setNotice('Deal-level discount updated.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update deal discount');
    } finally {
      setSavingDeal(false);
    }
  };

  const onConvertQuote = async () => {
    if (!accessToken || !quote) return;
    setSubmitting(true);
    setError('');
    try {
      const order = await commerceApi.convertQuote(accessToken, quote.id);
      setNotice('Quote converted to order.');
      navigate(`/shop/orders/${order.id}`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to convert quote');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="content-wrap fade-in">
      <div className="content-head row-between">
        <h1>Quote</h1>
        <Link to="/shop/orders" className="ghost-link">Back to Orders</Link>
      </div>
      {error && <div className="error-text">{error}</div>}

      {quote && (
        <div className="quote-layout">
          <div className="quote-items card">
            <h3>Quote #{quote.public_id}</h3>
            <p className="mini-note">Status: {quote.status}</p>

            <div className="quote-section">
              <h4>Devices</h4>
              <table className="cart-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Qty</th>
                    <th>List Price</th>
                    <th>Final Unit</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {deviceLines.map((line) => (
                    <Fragment key={line.id}>
                      <tr>
                        <td>{lineName(line)}</td>
                        <td>{line.qty}</td>
                        <td>${lineListPrice(line).toFixed(2)}</td>
                        <td>${lineUnit(line).toFixed(2)}</td>
                        <td>${(lineUnit(line) * line.qty).toFixed(2)}</td>
                      </tr>
                      {(serviceLinesByParent.get(line.id) || []).map((svc) => (
                        <tr key={svc.id}>
                          <td className="quote-nested-line">
                            ↳ {lineName(svc)} {svc.parent_line_id ? `(attached to ${lineName(lineById.get(svc.parent_line_id) || svc)})` : ''}
                          </td>
                          <td>{svc.qty}</td>
                          <td>${lineListPrice(svc).toFixed(2)}</td>
                          <td>${lineUnit(svc).toFixed(2)} / {svc.interval?.toLowerCase() || 'period'}</td>
                          <td>${(lineUnit(svc) * svc.qty).toFixed(2)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                  {deviceLines.length === 0 && (
                    <tr>
                      <td className="mini-note" colSpan={5}>No devices in this quote.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="quote-section">
              <h4>Services</h4>
              <table className="cart-table">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Qty</th>
                    <th>List Price</th>
                    <th>Final Rate</th>
                    <th>Recurring</th>
                  </tr>
                </thead>
                <tbody>
                  {serviceLines.map((line) => (
                    <tr key={line.id}>
                      <td>{lineName(line)}</td>
                      <td>{line.qty}</td>
                      <td>${lineListPrice(line).toFixed(2)}</td>
                      <td>${lineUnit(line).toFixed(2)}/{line.interval?.toLowerCase() || 'period'}</td>
                      <td>${(lineUnit(line) * line.qty).toFixed(2)}</td>
                    </tr>
                  ))}
                  {serviceLines.length === 0 && (
                    <tr>
                      <td className="mini-note" colSpan={5}>No managed services in this quote.</td>
                    </tr>
                  )}
                </tbody>
              </table>
              {orphanServices.length > 0 && <p className="mini-note">Some services are not attached to a device line.</p>}
            </div>
          </div>

          <aside className="quote-summary card">
            <h3>Totals</h3>
            <div className="billing-row">
              <span>Default discount</span>
              <strong>{((quote.default_discount_pct || 0) * 100).toFixed(2)}%</strong>
            </div>
            <div className="billing-row">
              <span>Deal discount</span>
              <strong>{((quote.incremental_discount_pct || 0) * 100).toFixed(2)}%</strong>
            </div>
            <div className="billing-row">
              <span>One-time total</span>
              <strong>${quote.one_time_total.toFixed(2)}</strong>
            </div>
            <div className="billing-row">
              <span>Monthly total</span>
              <strong>${quote.monthly_total.toFixed(2)}</strong>
            </div>
            <div className="billing-row">
              <span>Projected 12-month</span>
              <strong>${quote.projected_12_month_cost.toFixed(2)}</strong>
            </div>
            <div className="billing-row">
              <span>Estimated tax</span>
              <strong>${estimatedTax.toFixed(2)}</strong>
            </div>
            <div className="billing-row">
              <span>Estimated shipping</span>
              <strong>${estimatedShipping.toFixed(2)}</strong>
            </div>
            <div className="billing-row total">
              <span>Estimated due today</span>
              <strong>${estimatedDueToday.toFixed(2)}</strong>
            </div>
            <div className="billing-row">
              <span>Payment validation</span>
              <strong>{onboarding?.payment_validation_status || 'PENDING'}</strong>
            </div>

            {canManagePricing && (
              <div className="discount-config-box">
                <h4>Pricing Controls</h4>
                <label>Default tenant discount (%)</label>
                <div className="discount-action-row">
                  <input
                    type="number"
                    min="0"
                    max="95"
                    step="0.01"
                    value={defaultDiscountInput}
                    onChange={(e) => setDefaultDiscountInput(e.target.value)}
                  />
                  <button className="secondary-btn" onClick={onApplyDefaultDiscount} disabled={savingDefault}>
                    {savingDefault ? 'Saving...' : 'Apply'}
                  </button>
                </div>
                <label>Deal incremental discount (%)</label>
                <div className="discount-action-row">
                  <input
                    type="number"
                    min="0"
                    max="95"
                    step="0.01"
                    value={incrementalDiscountInput}
                    onChange={(e) => setIncrementalDiscountInput(e.target.value)}
                  />
                  <button className="secondary-btn" onClick={onApplyDealDiscount} disabled={savingDeal}>
                    {savingDeal ? 'Saving...' : 'Apply'}
                  </button>
                </div>
              </div>
            )}

            <button
              className="secondary-btn"
              onClick={onSendQuote}
              disabled={!canSendQuote || sending || quote.status === 'SENT' || quote.status === 'CONVERTED'}
            >
              {sending ? 'Sending...' : 'Send Quote'}
            </button>
            <button className="secondary-btn" onClick={onAcceptQuote} disabled={accepting || quote.status === 'ACCEPTED' || quote.status === 'CONVERTED'}>
              {accepting ? 'Accepting...' : 'Accept / Approve BAFO'}
            </button>
            <button
              className="secondary-btn"
              onClick={async () => {
                if (!accessToken) return;
                try {
                  const updated = await commerceApi.validatePaymentMethod(accessToken, {
                    payment_method_type: 'MANUAL',
                    external_reference: (quote.public_id || quote.id).replace(/\s+/g, '-').toLowerCase(),
                  });
                  setOnboarding(updated);
                  setNotice('Payment method validated.');
                } catch (err: any) {
                  setError(err?.response?.data?.detail || 'Failed to validate payment method');
                }
              }}
            >
              Validate Payment
            </button>
            <button
              className="primary-btn"
              onClick={onConvertQuote}
              disabled={!canConvertQuote || submitting || quote.status !== 'ACCEPTED' || onboarding?.payment_validation_status !== 'VERIFIED'}
            >
              {submitting ? 'Converting...' : 'Convert to Order'}
            </button>
            <button className="ghost-btn" disabled>Download PDF (later)</button>
            {(!canSendQuote || !canConvertQuote) && (
              <div className="mini-note">Send/Convert actions depend on your assigned permissions.</div>
            )}
          </aside>
        </div>
      )}
      {notice && <div className="toast-notice">{notice}</div>}
    </section>
  );
};
