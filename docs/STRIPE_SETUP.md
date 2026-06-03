# Stripe Integration — Developer Setup

## Overview

SecureOffice2 uses **Stripe Checkout (hosted)** for payments. Customers click a button in the app, get redirected to Stripe's checkout page, pay, and get redirected back. Webhooks handle all payment confirmation server-side.

## Architecture

```
User clicks "Subscribe" → Backend creates Checkout Session → Redirect to Stripe
                                                                    ↓
User completes payment on Stripe's hosted page
                                                                    ↓
Stripe redirects to /billing/success ← Frontend shows confirmation
Stripe sends webhook to /billing/stripe/webhook ← Backend records Payment/Subscription
```

## Local Development Setup

### 1. Get Stripe test-mode API keys

- Go to https://dashboard.stripe.com/test/apikeys
- Copy **Secret key** (`sk_test_…`) and **Publishable key** (`pk_test_…`)

### 2. Install the Stripe CLI

```bash
brew install stripe/stripe-cli/stripe
stripe login
```

This opens a browser for authentication. The CLI key expires after 90 days — just re-run `stripe login` when it does.

### 3. Start the webhook listener

```bash
stripe listen --forward-to http://localhost:8000/billing/stripe/webhook
```

This prints a **webhook signing secret** (`whsec_…`). Copy it — you'll need it in the next step.

> **Keep this terminal running** while testing. It forwards Stripe events to your local backend.

### 4. Configure environment variables

**`backend/.env`** — add these:

```env
STRIPE_SECRET_KEY=sk_test_…your_secret_key…
STRIPE_PUBLISHABLE_KEY=pk_test_…your_publishable_key…
STRIPE_WEBHOOK_SECRET=whsec_…from_stripe_listen…
STRIPE_SUCCESS_URL=http://localhost:5173/billing/success?session_id={CHECKOUT_SESSION_ID}
STRIPE_CANCEL_URL=http://localhost:5173/billing/cancelled
```

> `{CHECKOUT_SESSION_ID}` is a Stripe template variable — Stripe replaces it automatically at redirect time. Do not change it.

**`frontend/.env`** — add these:

```env
VITE_STRIPE_PUBLISHABLE_KEY=pk_test_…your_publishable_key…
VITE_STRIPE_DEFAULT_PRICE_ID=price_…your_price_id…
```

To get a Price ID: create a product in the [Stripe Dashboard](https://dashboard.stripe.com/test/products) → copy the Price ID from the pricing section (starts with `price_`).

### 5. Start the app

```bash
# Terminal 1 — webhook listener (already running from step 3)
stripe listen --forward-to http://localhost:8000/billing/stripe/webhook

# Terminal 2 — backend
cd backend && uvicorn app.main:app --reload

# Terminal 3 — frontend
cd frontend && npm run dev
```

### 6. Test a payment

1. Log in at `http://localhost:5173`
2. Go to **Billing** → click **Subscribe**
3. On the Stripe Checkout page, use these test credentials:
   - Card: `4242 4242 4242 4242`
   - Expiry: any future date (e.g. `12/30`)
   - CVC: any 3 digits (e.g. `123`)
4. You'll be redirected to `/billing/success`
5. Check the `stripe listen` terminal — you should see webhook events like `checkout.session.completed`, `invoice.paid`

### Other test cards

| Card number          | Scenario                   |
|----------------------|----------------------------|
| `4242 4242 4242 4242` | Successful payment         |
| `4000 0000 0000 3220` | 3D Secure authentication   |
| `4000 0000 0000 9995` | Declined (insufficient funds) |

Full list: https://docs.stripe.com/testing#cards

## Production Deployment

In production there is **no Stripe CLI**. Instead:

1. Go to [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks)
2. Click **Add endpoint**
3. URL: `https://yourdomain.com/billing/stripe/webhook`
4. Select events: `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`
5. Copy the **Signing secret** (`whsec_…`) → set as `STRIPE_WEBHOOK_SECRET` in production env
6. Use **live-mode** API keys (`sk_live_…`, `pk_live_…`) instead of test keys
7. Update `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL` to your production domain

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/services/stripe_service.py` | All Stripe SDK calls (only file that imports `stripe`) |
| `backend/app/services/stripe_webhook_handler.py` | Webhook event processing (idempotent) |
| `backend/app/routes/stripe.py` | API endpoints mounted at `/billing/stripe/` |
| `frontend/src/api/billingApi.ts` | Frontend API client for Stripe endpoints |
| `frontend/src/pages/BillingSuccessPage.tsx` | Post-checkout success page |
| `frontend/src/pages/BillingCancelledPage.tsx` | Checkout cancelled page |

## Troubleshooting

- **"Stripe Price ID not configured"** → Set `VITE_STRIPE_DEFAULT_PRICE_ID` in `frontend/.env` and restart the dev server
- **Webhook 400 errors** → The `STRIPE_WEBHOOK_SECRET` in `backend/.env` must match the one from `stripe listen`. Restart `stripe listen` and update the secret if they mismatch.
- **`stripe: command not found`** → Run `brew install stripe/stripe-cli/stripe`
- **CLI key expired** → Run `stripe login` again
