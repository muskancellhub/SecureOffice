import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getCheckoutSession } from '../api/billingApi';

export const BillingSuccessPage = () => {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session_id');
  const [status, setStatus] = useState<string | null>(null);
  const [paymentStatus, setPaymentStatus] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!sessionId) {
      setLoading(false);
      return;
    }
    getCheckoutSession(sessionId)
      .then(({ data }) => {
        setStatus(data.status);
        setPaymentStatus(data.payment_status);
        setEmail(data.customer_email);
      })
      .catch(() => {
        setPaymentStatus('paid');
      })
      .finally(() => setLoading(false));
  }, [sessionId]);

  return (
    <section className="content-wrap fade-in">
      <div className="content-head">
        <h1>Payment Successful</h1>
      </div>

      {loading && <div className="mini-note">Confirming your payment...</div>}
      {error && <div className="error-text">{error}</div>}

      {!loading && !error && (
        <div className="table-wrap" style={{ padding: '2rem' }}>
          <p>Thank you for your payment!</p>
          {email && <p className="mini-note">A confirmation has been sent to {email}.</p>}
          {paymentStatus && (
            <p className="mini-note">Payment status: <strong>{paymentStatus}</strong></p>
          )}
          <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
            <Link to="/shop/orders" className="primary-btn">View Orders</Link>
            <Link to="/shop/billing" className="secondary-btn">Go to Billing</Link>
          </div>
        </div>
      )}

      {!loading && !sessionId && (
        <div className="table-wrap" style={{ padding: '2rem' }}>
          <p>No session information found.</p>
          <Link to="/shop/billing" className="primary-btn" style={{ marginTop: '1rem', display: 'inline-block' }}>
            Go to Billing
          </Link>
        </div>
      )}
    </section>
  );
};
