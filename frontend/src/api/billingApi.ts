import { api } from './client';

export const startSubscriptionCheckout = (priceId: string) =>
  api.post<{ url: string }>('/billing/stripe/checkout/subscription', { price_id: priceId });

export const startOrderCheckout = (orderId: string) =>
  api.post<{ url: string }>(`/billing/stripe/checkout/order/${orderId}`);

export const getCheckoutSession = (sessionId: string) =>
  api.get<{ status: string; payment_status: string; customer_email: string | null }>(
    `/billing/stripe/session/${sessionId}`,
  );
