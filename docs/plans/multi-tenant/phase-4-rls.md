# Phase 4 — Postgres Row-Level Security  ✅ BUILT

Defense-in-depth hardening. App-layer guards (Phases 0–3) already scope every
query; RLS makes the database refuse cross-tenant rows even if a query forgets a
`WHERE tenant_id`. Ship last, behind a flag, after Phases 0–3 are stable.

> **Status (built 2026-06-05):** shipped behind `ENABLE_RLS` (default **off**).
> See "What actually shipped" at the bottom — several Postgres subtleties bit us.

## 1. Set the GUC per request — wire into the Phase 0 seam

In `app/middleware/tenant_context.py` / the request lifecycle, after resolving
`TenantContext`, run on the request's transaction:
```python
db.execute(text("SET LOCAL app.current_tenant_id = :t"), {"t": ctx.effective_tenant_id})
```
`SET LOCAL` is transaction-scoped, so **one transaction per request** is required.
Verify the session/pooling setup (`app/core/database.py`, `get_db`) opens a txn per
request and doesn't reuse a connection across requests without reset. For a SUPER_ADMIN
acting cross-tenant the GUC carries the **active** tenant (not the actor's home), so RLS
naturally allows the intended cross-tenant access.

## 2. Enable RLS + policy on every tenant-scoped table

```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <t>
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
```
Tables (all that carry `tenant_id`): `users`, `quotes`, `orders`, `contracts`,
`subscriptions`, `invoices`, `payments`, `assets`, `network_designs`, `carts`,
`customer_pricing`, `customer_price_overrides`, `list_prices`,
`tenant_order_notification_settings`, `tenant_onboarding`, `financing_terms` (Phase 1),
`tenant_settings` (Phase 3).

**Do NOT enable RLS on the shared catalog tables** (`products`, `product_components`,
`bundles`, `bundle_items`, `catalog_items`) — they're intentionally global and have no
`tenant_id`.

## 3. Critical caveats
- **`current_setting(..., true)`** (the `true` = missing_ok) returns NULL when the GUC is
  unset, so the policy denies all rows rather than erroring. Decide what unauthenticated /
  system paths (migrations, startup seeds, cron) need — they may have to run as a role with
  `BYPASSRLS` or set the GUC explicitly. The migration runner itself must not be locked out.
- **Table owners and superusers bypass RLS by default.** The app's DB role must be a
  *non-owner* with `FORCE ROW LEVEL SECURITY` on each table, or the policy is silently a no-op.
- **Backfills / clone-on-onboard** run before a tenant context exists — set the GUC to the
  master/target tenant inside those operations, or run them with bypass.
- Roll out **behind a feature flag / per-table** so a policy mistake doesn't take down all
  reads at once. Test each table's policy with a non-super and a super session.

## Acceptance
- With `app.current_tenant_id = <dell>`, a raw `SELECT * FROM quotes` returns only Dell rows.
- A query that *forgets* `WHERE tenant_id` still cannot read another tenant's rows.
- SUPER_ADMIN with `X-Tenant-Id: <dell>` reads/writes Dell; without the header, home tenant.
- Migrations, startup seeds, and the master-tenant seed still run (not locked out by RLS).

## Gotchas
- Connection pooling + `SET LOCAL`: if a pooler (PgBouncer in transaction mode) is in front,
  confirm `SET LOCAL` survives to the actual query. Session-pooling or `SET` reset on checkin
  matters here.
- ORM bulk operations and joins across a non-RLS shared table + an RLS table are fine, but
  watch for `INSERT ... RETURNING` paths where the new row's `tenant_id` must satisfy the
  `WITH CHECK` clause — add `WITH CHECK (tenant_id = current_setting(...)::uuid)` to the policy
  if you want writes constrained too (recommended).

---

## What actually shipped

Behind `ENABLE_RLS` (env, default `false`). Off ⇒ byte-identical to Phase 3.

### Files
| File | Change |
|------|--------|
| `app/core/config.py` | `enable_rls: bool = False` (`ENABLE_RLS`). |
| `app/core/database.py` | **GUC plumbing.** `get_db(request)` resolves the request's *effective* tenant (JWT tenant, or `X-Tenant-Id` for SUPER_ADMIN) and stashes it on `session.info['tenant_id']`. A `Session` **`after_begin` event listener** issues `SELECT set_config('app.current_tenant_id', :t, true)` (= parameterised `SET LOCAL`) on **every transaction** — guarded by `enable_rls` and a no-op when the session has no tenant. |
| `app/core/runtime_migrations.py` | `_apply_rls_policies(conn)` at the end of the migration: bidirectional. On ⇒ `ENABLE`+`FORCE ROW LEVEL SECURITY` + `tenant_isolation` policy per tenant-scoped table; off ⇒ drop policy + `NO FORCE` + `DISABLE`. Each table guarded by an `information_schema` `tenant_id`-column check. |
| `backend/.env.example` | Documents `ENABLE_RLS`. |
| `tests/test_rls.py` | GUC-survives-commits, read isolation, unset-GUC-sees-all, WITH CHECK blocks foreign-tenant write. Enforcement asserts skip if the DB role is a superuser. |

### The policy (and why it looks like that)
```sql
USING (
  NULLIF(current_setting('app.current_tenant_id', true), '') IS NULL
  OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
)
WITH CHECK ( ...same... )
```
- **`true` (missing_ok)** so an unset GUC returns NULL instead of erroring.
- **`NULLIF(..., '')`** — THE bite: a *custom* GUC, once set then reset at transaction
  end, reverts to an **empty string `''`**, not NULL, and that value lingers on the
  **pooled** connection. Without the `NULLIF`, a later request with no tenant hit
  `''::uuid` → `invalid input syntax for type uuid: ""`. Both NULL and `''` must mean
  "no tenant context → allow all" (migrations, seeds, cron, unauthenticated paths).

### Hard-won notes (read before touching this)
- **`after_begin`, not a one-shot SET.** Services `commit()` several times per request;
  each commit ends the transaction and discards `SET LOCAL`. Re-applying on every
  `after_begin` is what makes RLS hold across a whole request.
- **`session.info`, not a contextvar.** `get_db` stashes the tenant on the session and the
  listener reads it there — avoids the BaseHTTPMiddleware contextvar-propagation gotcha and
  needs no per-route wiring (every route already depends on `get_db`).
- **`FORCE` is mandatory** — without it the table *owner* (the app role) bypasses RLS and the
  policy is a silent no-op. **But a SUPERUSER role bypasses RLS even with FORCE** — the app
  must connect as a non-superuser owner. Verified here: `secureoffice_app` is non-superuser,
  so enforcement is real (tests confirm read isolation + write rejection).
- **System paths stay open.** The migration runner uses a Core connection (the `after_begin`
  Session event doesn't fire) and startup seeds use bare `SessionLocal()` with no tenant —
  both leave the GUC unset, so the "allow all" branch keeps them working. Nothing gets locked out.
- **Kill switch.** Flip `ENABLE_RLS=false` and the next boot drops every policy and disables
  RLS. A crashed test that left it on self-heals on the next default-off migration. Verified:
  after the on→off cycle, `pg_class.relrowsecurity` is false everywhere and 0 policies remain.
- **Shared catalog excluded.** `products`, `product_components`, `bundles`, `bundle_items`,
  `catalog_items` have no `tenant_id` and get no policy (intentionally global).

### Verification
- `pytest tests/test_rls.py` → 4 passed (against the non-superuser `secureoffice_app` role).
- Full suite: **20 failed / 98 passed / 0 errors** — the 20 are the unchanged pre-existing
  `test_unified_catalog_and_bom` + `test_network_design_service` set. The RLS module's
  teardown disabled RLS, so all later modules pass.
- Post-suite DB state: RLS disabled on all tables, 0 `tenant_isolation` policies (kill switch clean).
- `TestClient GET /tenants` (unauth) → 401 (not 500): confirms `get_db(request)` still resolves.
