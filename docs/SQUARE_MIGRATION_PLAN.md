# Stripe → Square Migration Plan (Sandbox Only)

**Status:** Draft · **Date:** 2026-06-26 · **Scope:** Development / Sandbox only — **no production changes**

---

## 1. Goal & scope

Replace the current Stripe payment integration with **Square**, using Square's
**Web Payments SDK** so the buyer pays through an embedded card widget on our own
page (Apple Pay / Google Pay / Cash App / card), instead of being redirected to a
hosted page.

In scope (now):

- Wire up Square in the **Sandbox** environment only.
- Add a Square payment service + routes on the FastAPI backend.
- Replace the Stripe checkout call in the React Billing UI with the Square widget.
- Track/reconcile payments via Square's `GetOrder` / webhooks, mirrored into our DB.

Out of scope (explicitly **not** now):

- Anything touching **production** Square (`connect.squareup.com`), real cards, or
  real money. Production cutover is documented in §11 as a *future* step only.
- Removing Stripe code permanently — we leave it in place behind a flag until
  Square is validated (§10).

---

## 2. Current Stripe integration (what exists today)

The project is **FastAPI (Python) backend + React/TS (Vite) frontend**. Stripe is
wired in as follows:

**Backend**

| File | Role |
|---|---|
| `backend/app/services/stripe_service.py` | Creates Stripe Checkout Sessions (subscription + order), customer mgmt, webhook verify, session retrieve |
| `backend/app/routes/stripe.py` | Routes under `/billing/stripe`: `checkout/subscription`, `checkout/order/{id}`, `session/{id}`, `webhook` |
| `backend/app/services/stripe_webhook_handler.py` | Idempotent webhook event handling → writes `Invoice` / `Payment` / `Subscription` rows |
| `backend/app/core/config.py` | Settings: `stripe_secret_key`, `stripe_publishable_key`, `stripe_webhook_secret`, `stripe_success_url`, `stripe_cancel_url` |
| `backend/app/models/lifecycle.py` | `PaymentMethod` enum (`MANUAL`, `CARD`, `BANK_TRANSFER`, `STRIPE`); `Invoice`, `Payment`, `Subscription` models |

**Frontend**

| File | Role |
|---|---|
| `frontend/src/api/billingApi.ts` | `startSubscriptionCheckout`, `startOrderCheckout`, `getCheckoutSession` |
| `frontend/src/pages/BillingPage.tsx` | "Add a card" / subscribe button → calls checkout, then `window.location.assign(url)` (redirect) |
| `frontend/.env.example` | `VITE_STRIPE_DEFAULT_PRICE_ID` |

**Key observation:** the current Stripe flow is **redirect-based hosted Checkout**
(both subscription and one-time order). Moving to the Square **Web Payments SDK**
keeps the buyer on our page instead — a UX upgrade, but it changes the frontend
flow from "redirect" to "embedded widget + tokenize + confirm".

---

## 3. Chosen approach: Web Payments SDK (embedded widget)

- **Frontend** loads Square's `square.js`, renders the card/wallet widget, and
  tokenizes the card in the browser (the card number lives inside Square's iframe —
  it never hits our servers).
- **Backend** receives the one-time **token (nonce)** and calls Square's
  `CreatePayment` API (`POST /v2/payments`) to charge it.
- **Confirmation** comes from `GetOrder` / `GetPayment` and from **webhooks**.

PCI posture: card data is tokenized by Square, so we stay in the light tier
(SAQ A-EP). No raw card data in our DB. (No PCI paperwork applies to sandbox dev.)

> Note: the manager's docs describe the **Payment Links / Quick Pay** redirect flow
> (`/v2/online-checkout/payment-links`). That's a valid alternative and lower
> effort, but it is a redirect, not an embedded widget. This plan implements the
> **widget**. The same backend credentials/config work for either, so we can fall
> back to Payment Links if needed.

---

## 4. Payment flow (one-time order)

```
React BillingPage
   │  1. load square.js (sandbox), init payments(appId, locationId)
   │  2. buyer enters card in Square widget → card.tokenize() → { token }
   ▼
POST /billing/square/payment   { order_id, source_id: token, idempotency_key }
   │  (FastAPI)
   ▼
square_service.create_payment()
   │  3. POST https://connect.squareupsandbox.com/v2/payments
   │     headers: Authorization: Bearer <sandbox token>, Square-Version, Content-Type
   │     body: { source_id, idempotency_key, amount_money, location_id, ... }
   ▼
Square Sandbox  ──►  payment CAPTURED  ──►  webhook: payment.updated
   │
   ▼
square_webhook_handler  →  write Invoice + Payment (method=SQUARE) rows
   │
   ▼
Frontend polls GetPayment / shows success
```

Subscription / card-on-file flow (Phase 2 — see §10) is more involved: tokenize →
create **Card on file** (Cards API) → **Subscriptions API**. Flagged as a separate
phase because it's heavier than one-time payments.

---

## 5. Sandbox configuration

All values live in environment files (`.env`), **never** committed and **never**
hardcoded. Sandbox host is `connect.squareupsandbox.com`.

**Backend `.env` (new keys):**

```env
SQUARE_ENV=sandbox
SQUARE_API_BASE=https://connect.squareupsandbox.com
SQUARE_VERSION=2025-01-23
SQUARE_ACCESS_TOKEN=<sandbox access token>      # secret — backend only
SQUARE_LOCATION_ID=L3FK3VQ9FZGM6
SQUARE_WEBHOOK_SIGNATURE_KEY=<from Developer Console webhook subscription>
SQUARE_SUCCESS_URL=http://localhost:5173/billing?status=success
SQUARE_CANCEL_URL=http://localhost:5173/billing?status=cancel
```

**Frontend `.env` (new keys):**

```env
VITE_SQUARE_ENV=sandbox
VITE_SQUARE_APP_ID=sandbox-sq0idb-Bnjz1ucjSILCnsGnVmltsQ
VITE_SQUARE_LOCATION_ID=L3FK3VQ9FZGM6
# script: https://sandbox.web.squarecdn.com/v1/square.js  (prod drops "sandbox.")
```

**Your sandbox values** belong only in a local, gitignored `.env` — never in this
doc or any committed file.

- Application ID: `sandbox-sq0idb-Bnjz1ucjSILCnsGnVmltsQ`  *(publishable)*
- Location ID: `L3FK3VQ9FZGM6`  *(publishable)*
- Access token: **REDACTED.** The sandbox token originally pasted here was exposed
  in chat, so it must be **rotated** in the Square Developer Console; keep the new
  value only in `backend/.env` (`SQUARE_ACCESS_TOKEN`).

App ID + Location ID are browser-safe (publishable). The **access token is secret** —
backend only, never in the React bundle.

---

## 6. Backend changes (FastAPI)

1. **Config** (`core/config.py`): add the `square_*` settings fields mirroring the
   `.env` keys above (Pydantic `Field(..., alias=...)`).
2. **New service** `services/square_service.py`:
   - `create_payment(order, source_id, idempotency_key)` → `POST /v2/payments`
     with `amount_money` (cents), `location_id`, `source_id`. Use `httpx`/`requests`
     with the `Authorization: Bearer`, `Square-Version`, `Content-Type` headers.
   - `get_payment(payment_id)` / `get_order(order_id)` for confirmation.
   - `verify_webhook(body, signature, url)` using `SQUARE_WEBHOOK_SIGNATURE_KEY`.
   - (Phase 2) `create_card_on_file`, `create_subscription`.
3. **New routes** `routes/square.py` under `/billing/square`:
   - `POST /payment` — body `{ order_id, source_id, idempotency_key }`; auth +
     tenant/order ownership checks (mirror the existing Stripe order route).
   - `GET /payment/{id}` — status lookup for the frontend.
   - `POST /webhook` — verify signature → dispatch to handler.
   - Register the router in `app/main.py`.
4. **Webhook handler** `services/square_webhook_handler.py`: idempotent
   (reuse the `stripe_events`-style table pattern → `square_events`), map
   `payment.updated` / `order.updated` → `Invoice` + `Payment` rows.
5. **Model**: add `SQUARE = 'SQUARE'` to `PaymentMethod` enum in
   `models/lifecycle.py`; reuse `Payment.external_reference` to store the Square
   `payment_id`. Add a `square_events` table + (optional) `tenant.square_customer_id`.

---

## 7. Frontend changes (React)

1. **Load `square.js`** (sandbox CDN) and initialize `Square.payments(appId, locationId)`.
2. **New component** `SquarePaymentForm.tsx`: mounts the card (and optionally
   Apple/Google/Cash App) widget, calls `card.tokenize()`, handles errors.
3. **API** `api/billingApi.ts`: add `createSquarePayment(orderId, sourceId)` →
   `POST /billing/square/payment`; `getSquarePayment(id)`.
4. **BillingPage.tsx**: replace the `onSubscribe` redirect (`window.location.assign`)
   with the embedded `SquarePaymentForm`; on success refresh billing data.
5. **`.env.example`**: add the `VITE_SQUARE_*` keys; mark `VITE_STRIPE_*` legacy.

---

## 8. Webhooks (sandbox)

- Create a **Sandbox webhook subscription** in the Developer Console pointing at a
  publicly reachable dev URL (use a tunnel like ngrok/cloudflared for local).
- Subscribe to `payment.updated` and `order.updated`.
- Copy the **signature key** into `SQUARE_WEBHOOK_SIGNATURE_KEY` and verify every
  incoming request before processing (reject on mismatch — mirror the Stripe
  signature-verification behavior).

---

## 9. Tracking & reconciliation

- **Square is the system of record.** Test payments are visible in the **Sandbox
  Seller Dashboard** (Developer Console → Sandbox test accounts → open Dashboard).
- **App-side**, we mirror a thin reference per payment: `order_id`, Square
  `payment_id` (in `Payment.external_reference`), `status`, `amount`, `currency`,
  timestamp — so Billing history works without re-querying Square.
- Reconciliation = on webhook (or on-demand `GetPayment`), upsert the `Payment`
  row and flip the `Invoice` to `PAID`, exactly as the Stripe handler does today.

---

## 10. Implementation phases / task list

**Phase 0 — Setup**
- [ ] Create/confirm sandbox app + test account; capture appId, token, location. *(manual — Developer Console)*
- [x] Add `square_*` env keys to backend & frontend `.env.example` (+ settings). *(fill real values into local `.env`)*

**Phase 1 — Backend (one-time payment)** — ✅ done
- [x] Add `square_*` settings + `PAYMENTS_PROVIDER` to `config.py`.
- [x] `square_service.py`: `create_payment`, `get_payment`, `verify_webhook` (HMAC-SHA256).
- [x] `routes/square.py`: `/payment`, `/payment/{id}`, `/webhook`; registered in `main.py`.
- [x] `PaymentMethod.SQUARE` + `square_events` table + `payments.method` CHECK refresh + webhook handler.
- [x] Unit tests: `test_square_service.py` (7) + `test_square_webhook_handler.py` (8), all green.

**Phase 2 — Frontend (widget)** — ✅ done
- [x] Load `square.js` (once, env-aware CDN), build `SquarePaymentForm.tsx` (tokenize + charge).
- [x] `billingApi.ts` Square calls + `paymentsProvider()` flag; wired the widget into
      **`OrderDetailsPage`** "Pay with card" (real `order_id` lives there, not BillingPage).

**Phase 3 — Webhooks & tracking**
- [x] Signature verification (`x-square-hmacsha256-signature`, constant-time) + idempotent row writes (code + tests).
- [ ] Sandbox webhook subscription + tunnel (ngrok/cloudflared); set `SQUARE_WEBHOOK_SIGNATURE_KEY`. *(manual)*
- [ ] Verify Invoice/Payment rows written end-to-end against the live sandbox. *(manual)*

**Phase 4 — Validate & flag**
- [x] Put Square behind a `PAYMENTS_PROVIDER` / `VITE_PAYMENTS_PROVIDER` flag; Stripe code kept intact.
- [ ] End-to-end sandbox test with Square test cards (set provider=square + creds, place an order, pay). *(manual — §12)*

**Phase 5 (later) — Subscriptions** (only if needed): card-on-file + Subscriptions API.

---

## 11. Production cutover (FUTURE — do not do now)

When (and only when) approved, production differs by **config only**:

| Setting | Sandbox (now) | Production (later) |
|---|---|---|
| API host | `connect.squareupsandbox.com` | `connect.squareup.com` |
| `square.js` | `sandbox.web.squarecdn.com/v1/square.js` | `web.squarecdn.com/v1/square.js` |
| Access token | sandbox token | production token (**rotate the one leaked in chat**) |
| Application ID | `sandbox-sq0idb-…` | production app ID |
| Location ID | `L3FK3VQ9FZGM6` | production location (`L3E6DQ78AQ9HJ` per manager docs) |
| Money | fake (test cards) | **real cards, real charges** |

No code changes — just environment values. **The production access token from the
manager's docs was pasted into chat and should be rotated before any prod use.**

---

## 12. Testing (sandbox)

- Use Square's **sandbox test cards** (e.g. Visa `4111 1111 1111 1111`, any future
  expiry/CVV) — these never move real money.
- Verify: widget tokenizes → `CreatePayment` returns `CAPTURED` → webhook fires →
  `Invoice`/`Payment` rows created → payment shows in Sandbox Seller Dashboard.
- Test failure cards and declines; confirm idempotency (same key ⇒ no double charge).

---

## 13. Open items / risks

- **Subscriptions**: current Stripe has a subscription flow; Square equivalent is
  heavier (Phase 5). Confirm whether dev scope needs it now.
- **Webhook tunneling** required for local sandbox webhooks.
- **Testers in India**: see note below — sandbox testing works from anywhere; the
  location's *country* (not the tester's location) sets currency/payment methods.
  Square as a business does not operate in India, which only matters for a *real*
  production account, not sandbox dev.
