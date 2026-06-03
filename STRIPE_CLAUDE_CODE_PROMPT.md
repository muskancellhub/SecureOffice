# Claude Code Prompt — Stripe Integration (subscriptions + one-time, hosted Checkout)

Paste everything below the line into Claude Code from the repo root (`/Users/muskan/SecureOffice2`).

---

You are adding Stripe payments to the SecureOffice2 codebase. The project is a FastAPI + SQLAlchemy 2.0 + Postgres backend (`backend/`) with a React 18 + Vite + axios frontend (`frontend/`). The data model already has `Subscription`, `Invoice`, `Payment`, and `PaymentMethod` (enum: `MANUAL`, `CARD`, `BANK_TRANSFER`) in `backend/app/models/lifecycle.py`. The `Tenant` model is in `backend/app/models/tenant.py`. There is **no Alembic** — schema changes go in `backend/app/core/runtime_migrations.py` using `ALTER TABLE … ADD COLUMN IF NOT EXISTS` style (idempotent, run on every boot).

The Stripe integration must support **both** recurring subscriptions and one-time order payments, using **Stripe Checkout (hosted)**. The user already has Stripe test-mode keys in `.env`:

```
STRIPE_SECRET_KEY=sk_test_…
STRIPE_PUBLISHABLE_KEY=pk_test_…
STRIPE_WEBHOOK_SECRET=whsec_…        # from `stripe listen` for local
STRIPE_SUCCESS_URL=http://localhost:5173/billing/success?session_id={CHECKOUT_SESSION_ID}
STRIPE_CANCEL_URL=http://localhost:5173/billing/cancelled
```

And `frontend/.env` has `VITE_STRIPE_PUBLISHABLE_KEY=pk_test_…`.

## Scope (do all three sections)

### A. Database migration

Append idempotent ALTERs to `backend/app/core/runtime_migrations.py` (do **not** create Alembic files):

```sql
ALTER TABLE tenants            ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_stripe_customer_id ON tenants (stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

ALTER TABLE subscriptions      ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(64);
ALTER TABLE subscriptions      ADD COLUMN IF NOT EXISTS stripe_price_id        VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS ix_subscriptions_stripe_subscription_id ON subscriptions (stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;

ALTER TABLE invoices           ADD COLUMN IF NOT EXISTS stripe_invoice_id VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS ix_invoices_stripe_invoice_id ON invoices (stripe_invoice_id) WHERE stripe_invoice_id IS NOT NULL;

-- payments.external_reference already exists — reuse for payment_intent_id; no schema change there.

-- idempotency table for webhooks
CREATE TABLE IF NOT EXISTS stripe_events (
    id           VARCHAR(64) PRIMARY KEY,        -- Stripe event.id (evt_…)
    type         VARCHAR(128) NOT NULL,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload      JSONB NOT NULL
);
```

Then update the SQLAlchemy models to match:

- `backend/app/models/tenant.py` → add `stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)`
- `backend/app/models/lifecycle.py` → on `Subscription` add `stripe_subscription_id` and `stripe_price_id` (both `String(64)`, nullable). On `Invoice` add `stripe_invoice_id` (String(64), nullable, unique).
- Add `STRIPE = 'STRIPE'` to the `PaymentMethod` enum in `backend/app/models/lifecycle.py`.

Run the backend once after to confirm `apply_runtime_migrations()` succeeds against the local Postgres.

### B. Backend — config, service, routes

**B1. Config.** In `backend/app/core/config.py` add to the `Settings` class:

```python
stripe_secret_key: str = Field('', alias='STRIPE_SECRET_KEY')
stripe_publishable_key: str = Field('', alias='STRIPE_PUBLISHABLE_KEY')
stripe_webhook_secret: str = Field('', alias='STRIPE_WEBHOOK_SECRET')
stripe_success_url: str = Field('', alias='STRIPE_SUCCESS_URL')
stripe_cancel_url: str = Field('', alias='STRIPE_CANCEL_URL')
```

**B2. Requirements.** Add `stripe>=12.0.0,<13.0.0` to `backend/requirements.txt` and `pip install -r requirements.txt`.

**B3. Service.** Create `backend/app/services/stripe_service.py`:

- Module-level: `import stripe; stripe.api_key = get_settings().stripe_secret_key`
- Class `StripeService(db: Session)` with methods:
  - `get_or_create_customer(tenant: Tenant) -> str` — if `tenant.stripe_customer_id` set, return it; else `stripe.Customer.create(name=tenant.name, metadata={'tenant_id': str(tenant.id)})`, persist on tenant, return id.
  - `create_subscription_checkout(tenant: Tenant, price_id: str) -> str` — returns Checkout Session `url`. Uses `mode='subscription'`, `customer=<above>`, `line_items=[{'price': price_id, 'quantity': 1}]`, `success_url=settings.stripe_success_url`, `cancel_url=settings.stripe_cancel_url`, `client_reference_id=str(tenant.id)`.
  - `create_order_checkout(tenant: Tenant, order: Order) -> str` — `mode='payment'`. Build `line_items` from `order.lines` using `price_data` (currency, unit_amount in cents, product_data.name from line.name_snapshot). Pass `metadata={'order_id': str(order.id), 'tenant_id': str(tenant.id)}`. Same success/cancel URLs.
  - `verify_webhook(payload: bytes, sig_header: str) -> stripe.Event` — wraps `stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)`.
  - `retrieve_session(session_id: str)` — for the success page to confirm payment.

Do **not** scatter `import stripe` across the codebase — this service is the only file that imports the SDK directly.

**B4. Webhook handler.** Create `backend/app/services/stripe_webhook_handler.py` with `handle_event(db: Session, event: stripe.Event) -> None`. Must be **idempotent**: first INSERT into `stripe_events` with `ON CONFLICT (id) DO NOTHING`; if zero rows affected, return (already processed). Then dispatch by `event.type`:

- `checkout.session.completed` — if `mode == 'subscription'`, fetch the subscription via `stripe.Subscription.retrieve(session.subscription)`, create/update a `Subscription` row using `client_reference_id` as tenant_id, store `stripe_subscription_id` + `stripe_price_id`. If `mode == 'payment'`, look up the `Order` from `metadata.order_id` and create a `Payment` row (method=`STRIPE`, status=`SUCCEEDED`, `external_reference=session.payment_intent`).
- `invoice.paid` — find local Invoice via `stripe_invoice_id` or by tenant+subscription, create a `Payment` (method=`STRIPE`, status=`SUCCEEDED`, `external_reference=invoice.payment_intent`), mark invoice paid.
- `invoice.payment_failed` — mark local invoice in failed state; create Payment with status=`FAILED`.
- `customer.subscription.updated` / `.deleted` — sync `Subscription.status` (`ACTIVE`/`CANCELLED`/etc) and `end_date` if applicable.
- `payment_intent.succeeded` / `.payment_failed` — log only; the higher-level event handlers above are the source of truth.

Unknown event types: log and return (do not raise).

**B5. Routes.** Create `backend/app/routes/stripe.py`:

```python
router = APIRouter(prefix='/billing/stripe', tags=['Stripe'])
```

Endpoints:

- `POST /checkout/subscription` — body `{price_id: str}`. Auth via `get_current_user`. Resolves tenant from current user, calls `StripeService.create_subscription_checkout`, returns `{url: str}`.
- `POST /checkout/order/{order_id}` — Auth via `get_current_user`. Loads order, authorizes (user must belong to order's tenant), calls `create_order_checkout`, returns `{url: str}`.
- `GET /session/{session_id}` — Auth via `get_current_user`. Returns `{status, payment_status, customer_email}` from `retrieve_session`. Used by success page.
- `POST /webhook` — **no auth dep**. Reads raw body via `await request.body()`, extracts `stripe-signature` header, calls `StripeService.verify_webhook` (returns 400 on `SignatureVerificationError` or `ValueError`), then `stripe_webhook_handler.handle_event(db, event)`. Returns `{received: true}`.

Mount in `backend/app/main.py`: `from app.routes.stripe import router as stripe_router` and `app.include_router(stripe_router)`. Place it next to the existing `billing_router` include.

**Important webhook detail:** FastAPI dependency `Depends(get_db)` is fine, but the body must be read as raw bytes for signature verification. Do not use `Body(...)` or a Pydantic model on the webhook route. Use `request: Request` and `await request.body()`.

### C. Frontend — buttons, success/cancel pages, API client

**C1. API client.** Add `frontend/src/api/billingApi.ts`:

```ts
import { api } from './client';

export const startSubscriptionCheckout = (priceId: string) =>
  api.post<{ url: string }>('/billing/stripe/checkout/subscription', { price_id: priceId });

export const startOrderCheckout = (orderId: string) =>
  api.post<{ url: string }>(`/billing/stripe/checkout/order/${orderId}`);

export const getCheckoutSession = (sessionId: string) =>
  api.get<{ status: string; payment_status: string; customer_email: string | null }>(
    `/billing/stripe/session/${sessionId}`,
  );
```

**C2. Pages.** Create:

- `frontend/src/pages/BillingSuccessPage.tsx` — reads `session_id` from `useSearchParams`, calls `getCheckoutSession`, shows status. While loading, show spinner. On success, link back to `/shop/orders` and `/billing`.
- `frontend/src/pages/BillingCancelledPage.tsx` — static page with "Checkout cancelled" + link back to the page they came from (use `useNavigate(-1)`).

Style consistent with existing pages — look at `frontend/src/pages/BillingPage.tsx` for the Tailwind patterns and component layout used in the project; match it.

**C3. Router.** In `frontend/src/router/AppRouter.tsx`:

- Import the two new pages.
- Add `<Route path="/billing/success" element={<BillingSuccessPage />} />` and `<Route path="/billing/cancelled" element={<BillingCancelledPage />} />` at the top level (do **not** put them inside `ProtectedRoute` — Stripe redirect may land before session cookies are re-established; the page itself can show a "log in" CTA if needed, but the route must be reachable).

**C4. Buttons.** Wire two real callsites:

- In `frontend/src/pages/BillingPage.tsx` (or a subscriptions section if you find one), add an "Upgrade plan" / "Subscribe" button. For now, **hardcode a single `price_id`** read from `import.meta.env.VITE_STRIPE_DEFAULT_PRICE_ID` (also add this to `frontend/.env` as a placeholder `price_test_REPLACE_ME` — the user will fill it in with a real Stripe Price ID after Phase 0). On click: `startSubscriptionCheckout(priceId).then(({data}) => window.location.assign(data.url))`. Disable button while in-flight.
- In `frontend/src/pages/OrderDetailsPage.tsx`, add a "Pay with card" button when order status is in a payable state (use existing status enum — pick the equivalent of "pending payment"). On click: `startOrderCheckout(order.id).then(({data}) => window.location.assign(data.url))`.

**C5. Do not** install `@stripe/stripe-js` — we are using hosted Checkout, so the redirect is just `window.location.assign(url)`. The publishable key env var stays for future Elements use but isn't imported anywhere yet.

## Verification

1. Backend: `cd backend && uvicorn app.main:app --reload` boots without errors; `apply_runtime_migrations` log line appears.
2. Run `cd backend && pytest tests/ -x` — all existing tests still pass.
3. In a separate terminal: `stripe listen --forward-to http://localhost:8000/billing/stripe/webhook` (the user has the CLI installed). Copy the printed `whsec_…` into `.env` and restart uvicorn.
4. Frontend: `cd frontend && npm run build` succeeds with no new TS errors. `npm run dev` starts.
5. Manual: log in as a tenant user, go to Billing page, click Subscribe (requires user to first paste a real `price_…` into `VITE_STRIPE_DEFAULT_PRICE_ID`), complete checkout with card `4242 4242 4242 4242`, any future expiry, any CVC. Confirm redirect to `/billing/success`, then check Postgres:
   - `tenants.stripe_customer_id` populated
   - `subscriptions` row created with `stripe_subscription_id` + `stripe_price_id`
   - `stripe_events` table has 2–3 rows (checkout.session.completed, customer.subscription.created, invoice.paid)
   - `invoices` + `payments` rows created via webhook (not via redirect)

## Output

When done, print a report:

```
=== STRIPE INTEGRATION REPORT ===
Migration: applied | columns added: tenants.stripe_customer_id, subscriptions.stripe_subscription_id, ...
Backend service: app/services/stripe_service.py (<n> methods)
Backend webhook handler: app/services/stripe_webhook_handler.py (handles: <event types>)
Backend routes: app/routes/stripe.py mounted at /billing/stripe (<endpoints>)
Frontend API: src/api/billingApi.ts
Frontend pages: BillingSuccessPage, BillingCancelledPage
Frontend routes added: /billing/success, /billing/cancelled
Frontend buttons wired: <list of files+components>
Tests: <count> passed
Build: PASS|FAIL
Manual test: not run (requires real Stripe Price ID + interactive flow)

Next manual steps for the user:
1. Create a recurring Price in Stripe dashboard, paste id into VITE_STRIPE_DEFAULT_PRICE_ID
2. Run `stripe listen --forward-to http://localhost:8000/billing/stripe/webhook` and update STRIPE_WEBHOOK_SECRET
3. End-to-end test with card 4242 4242 4242 4242
```

## Constraints

- Do **not** install `@stripe/stripe-js` — hosted Checkout only.
- Do **not** create Alembic migrations — extend `runtime_migrations.py`.
- Do **not** put secret-key handling anywhere except `stripe_service.py`.
- Webhook handler must be idempotent — re-running the same event must not create duplicate Payments or Subscriptions.
- Authorize the order-checkout endpoint: a user from tenant A must not be able to start checkout for tenant B's order. Reuse `AuthorizationService` if it exists in the codebase.
- Do **not** commit; leave the working tree dirty for human review.
- Do **not** modify any unrelated code.

Begin.
