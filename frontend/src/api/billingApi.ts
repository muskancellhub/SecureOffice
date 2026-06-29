import { api } from './client';

// ── Square (embedded Web Payments widget) — the sole payment provider ───────
export interface SquarePaymentResult {
  payment_id: string | null;
  status: string | null;
  amount: number | null;
  currency: string | null;
}

// Charge a one-time card nonce (source_id) tokenized by the Square widget.
export const createSquarePayment = (orderId: string, sourceId: string, idempotencyKey?: string) =>
  api.post<SquarePaymentResult>('/billing/square/payment', {
    order_id: orderId,
    source_id: sourceId,
    idempotency_key: idempotencyKey,
  });

export const getSquarePayment = (paymentId: string) =>
  api.get<SquarePaymentResult>(`/billing/square/payment/${encodeURIComponent(paymentId)}`);
