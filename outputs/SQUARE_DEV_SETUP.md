# Adding Square to a Dev Environment (Sandbox)

A setup guide for integrating Square as a payment provider in a new project's
development environment. Uses the **Web Payments SDK** (embedded card widget):
the browser tokenizes the card inside Square's iframe and hands the backend a
one-time `source_id` (nonce), which the backend charges server-side. **No raw
card data ever touches your servers.**

Everything below targets **Sandbox**. Production is a config-only swap (host +
token + location id) — see the last section.

---

## 1. Prerequisites

- A Square Developer account: https://developer.squareup.com/
- A backend that can hold a secret (FastAPI/Node/etc.) and make HTTPS calls.
- A frontend that can load a script from Square's CDN.
- A tunnel (ngrok / cloudflared) if you want to test webhooks locally.

---

## 2. Get your sandbox credentials

In the **Square Developer Console** → your Application → **Sandbox**:

| Value | Where to find it | Secret? |
|-------|------------------|---------|
| **Application ID** (`sandbox-sq0idb-…`) | Sandbox → Credentials | No — publishable, browser-safe |
| **Location ID** | Sandbox → Locations | No — publishable, browser-safe |
| **Access Token** | Sandbox → Credentials | **YES — backend only, never in the frontend bundle or committed** |
| **Webhook Signature Key** | Sandbox → Webhooks → your subscription | **YES — backend only** |

> The App ID and Location ID are safe to ship to the browser. The **access token
> is a secret**: keep it only in the backend's local, gitignored `.env`. If a
> token is ever pasted into chat, a ticket, or a committed file, **rotate it** in
> the Console.

---

## 3. Environment variables

Keep all values in local `.env` files. **Never commit them** and never hardcode.
Add the keys (with placeholder values) to your `.env.example` so the next dev
knows what's required.

**Backend `.env`:**

```env
SQUARE_ENV=sandbox
SQUARE_API_BASE=https://connect.squareupsandbox.com
SQUARE_VERSION=2025-01-23
SQUARE_ACCESS_TOKEN=<sandbox access token>          # secret — backend only
SQUARE_LOCATION_ID=<your sandbox location id>
SQUARE_WEBHOOK_SIGNATURE_KEY=<from the webhook subscription>
# Optional: pin the exact URL registered in the Console when a tunnel rewrites
# scheme/host (otherwise signature verification falls back to the request URL).
SQUARE_WEBHOOK_NOTIFICATION_URL=
SQUARE_SUCCESS_URL=http://localhost:5173/billing?status=success
SQUARE_CANCEL_URL=http://localhost:5173/billing?status=cancel
```

**Frontend `.env` (Vite example — prefix accordingly for your framework):**

```env
VITE_SQUARE_ENV=sandbox
VITE_SQUARE_APP_ID=sandbox-sq0idb-<your app id>
VITE_SQUARE_LOCATION_ID=<your sandbox location id>
```

Notes:
- `SQUARE_VERSION` pins the Square API version sent as the `Square-Version`
  header. Bump deliberately, not automatically.
- The frontend gets **only** App ID + Location ID. The access token stays backend-side.

---

## 4. Backend integration

1. **Config** — add `square_*` settings that mirror the `.env` keys above (e.g.
   Pydantic `Field(alias=...)`, or your config loader's equivalent). Default the
   host to the sandbox URL so a missing var fails safe, not toward production.

2. **Service** — a `SquareService` (or module) that talks to the Square REST API
   over an HTTP client:
   - `create_payment(order, source_id, idempotency_key)` → `POST /v2/payments`
     with `amount_money` (integer **cents**), `location_id`, and `source_id`.
     Send `autocomplete=true` to capture immediately.
   - `get_payment(payment_id)` — status lookup for confirmation.
   - `verify_webhook(body, signature, url)` using the signature key (HMAC over
     `notification_url + raw body`, base64-compared).

   Required headers on every call:
   ```
   Authorization: Bearer <SQUARE_ACCESS_TOKEN>
   Square-Version: <SQUARE_VERSION>
   Content-Type: application/json
   ```
   Always pass an **idempotency key** on `create_payment` so retries don't double-charge.

3. **Routes** under a prefix like `/billing/square`:
   - `POST /payment` — body `{ order_id, source_id, idempotency_key }`; enforce
     auth **and** ownership (the order must belong to the caller/tenant) before
     charging.
   - `GET /payment/{id}` — status lookup for the frontend.
   - `POST /webhook` — verify the signature first, reject on mismatch, then dispatch.
   - Register the router with your app.

4. **Webhook handler** — make it **idempotent** (dedupe on Square's event id via
   a `square_events`-style table). Map `payment.updated` / `order.updated` onto
   your own payment/invoice records.

5. **Data model** — store a thin reference per payment: `order_id`, Square
   `payment_id`, `status`, `amount`, `currency`, timestamp. That lets billing
   history render without re-querying Square. **Square is the system of record;**
   your rows are a mirror.

Money handling: Square works in the **smallest currency unit** (cents). Convert
at the boundary — multiply by 100 outbound, divide by 100 for display.

---

## 5. Frontend integration

1. **Load the SDK** once, from the environment-appropriate CDN:
   - Sandbox: `https://sandbox.web.squarecdn.com/v1/square.js`
   - Production: `https://web.squarecdn.com/v1/square.js` (drops `sandbox.`)

   Guard against double-injection if multiple payment forms can mount.

2. **Initialize** `Square.payments(appId, locationId)`, then mount the card
   widget: `payments.card()` → `card.attach('#card-container')`.

3. **Tokenize on submit** — call `card.tokenize()`. On `status === 'OK'` you get
   a one-time `token` (the `source_id`). Post it to your backend
   `POST /billing/square/payment`; handle the `errors` array otherwise.

4. **On success** — refresh billing/order state from your backend (don't trust
   the client alone; the webhook is the authoritative confirmation).

The widget renders Square's own iframe, so card fields never live in your DOM.

---

## 6. Webhooks (local dev)

1. Start a tunnel: `ngrok http <backend-port>` (or `cloudflared`).
2. In the Console → **Sandbox** → Webhooks, create a subscription pointing at
   `https://<tunnel>/billing/square/webhook`.
3. Subscribe to `payment.updated` and `order.updated`.
4. Copy the **signature key** into `SQUARE_WEBHOOK_SIGNATURE_KEY`.
5. If the tunnel rewrites the host/scheme, set `SQUARE_WEBHOOK_NOTIFICATION_URL`
   to the exact registered URL so signature verification matches.
6. **Verify every incoming request** before processing — reject on mismatch.

---

## 7. Testing in sandbox

- Use Square's **sandbox test cards** (e.g. `4111 1111 1111 1111`, any future
  expiry, any CVV) — Square documents cards that force specific outcomes
  (approved, declined, CVV fail).
- Test payments appear in the **Sandbox Seller Dashboard** (Console → Sandbox
  test accounts → open Dashboard).
- Verify the full loop: widget tokenizes → backend charges → webhook fires →
  your invoice/payment record flips to paid.

---

## 8. Production cutover (later — do not do in dev)

It's a **config-only** change, no code edits:

- `SQUARE_ENV=production`
- `SQUARE_API_BASE=https://connect.squareup.com`
- Swap in the **production** access token and location id.
- Frontend loads `https://web.squarecdn.com/v1/square.js` and uses the
  production App ID / Location ID.
- Register a **production** webhook subscription and use its signature key.

---

## 9. Security checklist

- [ ] Access token and webhook signature key live **only** in backend `.env` (gitignored).
- [ ] `.env.example` lists the keys with placeholder values only.
- [ ] Frontend receives only App ID + Location ID.
- [ ] Webhook signatures verified on every request; mismatches rejected.
- [ ] Idempotency keys on every `create_payment`.
- [ ] Order ownership checked before charging.
- [ ] Any leaked token rotated in the Console immediately.
