import { useEffect, useRef, useState } from 'react';
import { Lock, X } from 'lucide-react';
import { createSquarePayment } from '../api/billingApi';
import type { SquarePaymentResult } from '../api/billingApi';
import { extractApiError } from '../utils/extractApiError';

// The Square Web Payments SDK attaches itself to window.Square once square.js
// loads. We keep the typing intentionally loose — the SDK has no first-party
// types bundled here, and we only touch a small, stable slice of it.
declare global {
  interface Window {
    Square?: any;
  }
}

const SQUARE_ENV = String(import.meta.env.VITE_SQUARE_ENV || 'sandbox').toLowerCase();
const APP_ID = import.meta.env.VITE_SQUARE_APP_ID as string | undefined;
const LOCATION_ID = import.meta.env.VITE_SQUARE_LOCATION_ID as string | undefined;
// Prod drops the "sandbox." prefix (docs/SQUARE_MIGRATION_PLAN.md §5/§11).
const SDK_URL =
  SQUARE_ENV === 'production'
    ? 'https://web.squarecdn.com/v1/square.js'
    : 'https://sandbox.web.squarecdn.com/v1/square.js';

let sdkPromise: Promise<void> | null = null;

// Load square.js exactly once across the app, even if several forms mount.
function loadSquareSdk(): Promise<void> {
  if (window.Square) return Promise.resolve();
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SDK_URL}"]`);
    if (existing) {
      existing.addEventListener('load', () => resolve());
      existing.addEventListener('error', () => reject(new Error('Failed to load square.js')));
      if (window.Square) resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = SDK_URL;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      sdkPromise = null;
      reject(new Error('Failed to load square.js'));
    };
    document.head.appendChild(script);
  });
  return sdkPromise;
}

// A fresh idempotency key is minted per payment attempt (see onPay). Each
// attempt re-tokenizes the card → a new single-use nonce → a new logical charge,
// so it must carry its own key. Reusing a key with different params (e.g. a
// changed amount after a failed first try) is what Square rejects with
// IDEMPOTENCY_KEY_REUSED. Concurrent double-submits are blocked by the
// disabled-button guard plus the single-use nonce.
function newIdempotencyKey(): string {
  const c: any = (typeof crypto !== 'undefined' && (crypto as any)) || null;
  if (c?.randomUUID) return c.randomUUID();
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

interface Props {
  orderId: string;
  amountLabel: string;
  onSuccess: (result: SquarePaymentResult) => void;
  onCancel: () => void;
}

export const SquarePaymentForm = ({ orderId, amountLabel, onSuccess, onCancel }: Props) => {
  const cardRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    let card: any = null;

    const init = async () => {
      if (!APP_ID || !LOCATION_ID) {
        setError('Square is not configured (missing VITE_SQUARE_APP_ID / VITE_SQUARE_LOCATION_ID).');
        return;
      }
      try {
        await loadSquareSdk();
        if (cancelled || !window.Square) return;
        const payments = window.Square.payments(APP_ID, LOCATION_ID);
        card = await payments.card();
        if (cancelled) return;
        await card.attach(containerRef.current);
        cardRef.current = card;
        if (!cancelled) setReady(true);
      } catch (err: any) {
        if (!cancelled) setError(err?.message || 'Failed to initialize the card form.');
      }
    };
    init();

    return () => {
      cancelled = true;
      // Detach to avoid leaking the iframe between mounts.
      try {
        card?.destroy?.();
      } catch {
        /* no-op */
      }
    };
  }, []);

  const onPay = async () => {
    if (!cardRef.current || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const result = await cardRef.current.tokenize();
      if (result.status !== 'OK' || !result.token) {
        const detail = result?.errors?.map((e: any) => e.message).join(' ') || 'Card details were rejected.';
        setError(detail);
        setSubmitting(false);
        return;
      }
      // Fresh key per attempt: a new nonce is a new logical charge, so reusing a
      // prior key (with a possibly different amount) would trip IDEMPOTENCY_KEY_REUSED.
      const { data } = await createSquarePayment(orderId, result.token, newIdempotencyKey());
      onSuccess(data);
    } catch (err: any) {
      setError(extractApiError(err, 'Payment failed. Please try again.'));
      setSubmitting(false);
    }
  };

  return (
    <div className="sqpay-backdrop" onClick={onCancel}>
      <div className="sqpay-shell" onClick={(e) => e.stopPropagation()}>
        <button className="sqpay-close" onClick={onCancel} aria-label="Close">
          <X size={18} />
        </button>
        <h3 className="sqpay-title">Pay {amountLabel}</h3>
        <p className="sqpay-sub">
          <Lock size={12} /> Card details are entered directly into Square and never touch our servers.
        </p>

        <div ref={containerRef} className="sqpay-card-container" />
        {!ready && !error && <p className="mini-note">Loading secure card form…</p>}
        {error && <div className="error-text sqpay-error">{error}</div>}

        <div className="sqpay-actions">
          <button className="sqpay-cancel-btn" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button className="sqpay-pay-btn" onClick={onPay} disabled={!ready || submitting}>
            {submitting ? 'Processing…' : `Pay ${amountLabel}`}
          </button>
        </div>
      </div>
    </div>
  );
};
