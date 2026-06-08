# Multi-Tenant Configuration Plan

> Goal: a CellHub **SUPER_ADMIN** selects an **active tenant** (Dell, Walmart, …) from one
> global filter and configures that tenant's settings in isolation — pricing, finances,
> admin/managed services, user access, and the design-ops queue. Order emails are already
> per-tenant and stay on their own page (excluded from the unified filter).

Decisions locked in:
- **Tenant filter:** global active-tenant switcher via `X-Tenant-Id` header + request context.
- **Global config tables:** become **fully per-tenant rows** (add `tenant_id`).
- **Isolation:** app-layer guard now, **Postgres RLS** as a hardening phase.
- **Settings storage:** hybrid — typed tables for money/pricing/financing, JSONB for soft toggles.

This doc is implementation-ready for Claude Code. Paths are relative to repo root.

---

## 0. Current state (verified in code)

**Already tenant-scoped** (every row has `tenant_id`):
`users`, `quotes`, `orders`, `contracts`, `subscriptions`, `invoices`, `payments`,
`assets`, `network_designs`, `carts`, `customer_pricing`, `list_prices`,
`customer_price_overrides`, `tenant_order_notification_settings`, `tenant_onboarding`.

**Still global — must become per-tenant:**
`financing_terms`, `catalog_items`, `products`, `product_components`, `bundles`, `bundle_items`.

**Role hierarchy already correct** (`backend/app/services/user_management_service.py`):
- `SUPER_ADMIN` can create `ADMIN` in any tenant (needs `manage_admins`); `_resolve_tenant_for_creation` already accepts a target tenant.
- `ADMIN` can only create/manage `USER` in their own tenant.
- `SUPER_ADMIN` accounts can't be created/edited from the console.

**Gaps blocking the goal:**
1. No single tenant filter — super-admins type raw tenant UUIDs into free-text boxes
   (`frontend/src/pages/AdminFinancingPage.tsx`, `AdminUserManagementPage.tsx`).
2. Most settings endpoints resolve tenant **only** from the JWT (`current_user['tenant_id']`),
   so a CellHub super-admin can't reach another tenant's config through them.
3. **Authz hole:** `PATCH /pricing/customers/{tenant_id}/commercial` and
   `POST /pricing/customers/{tenant_id}/price-overrides` accept any `tenant_id` with only a
   `manage_pricing` permission check — no SUPER_ADMIN / same-tenant assertion.
4. Admin routes aren't SUPER_ADMIN-gated at the router level
   (`frontend/src/router/AppRouter.tsx` — bare `<Route>`; pages do a loose `ADMIN || SUPER_ADMIN` check).

---

## 1. Active-tenant context (backend core)

**New:** `backend/app/middleware/tenant_context.py`

```python
# Resolves the effective tenant for the request.
# Returns a TenantContext(effective_tenant_id, is_cross_tenant).
def get_tenant_context(request, current_user, db) -> TenantContext:
    header = request.headers.get('X-Tenant-Id')
    actor_tenant = current_user['tenant_id']
    role = current_user['role']
    if header and header != actor_tenant:
        if role != 'SUPER_ADMIN':          # (optionally also user_type == 'CELLHUB')
            raise ForbiddenError('Cross-tenant access requires SUPER_ADMIN')
        if not TenantRepository(db).get_by_id(header):
            raise NotFoundError('Tenant not found')
        return TenantContext(effective_tenant_id=header, is_cross_tenant=True)
    return TenantContext(effective_tenant_id=actor_tenant, is_cross_tenant=False)
```

- Wire it as a FastAPI dependency alongside `get_current_user`.
- **Set the RLS GUC** on the request transaction:
  `db.execute(text("SET LOCAL app.current_tenant_id = :t"), {"t": ctx.effective_tenant_id})`.
- **Refactor the service layer** to take `tenant_id` from `TenantContext` instead of reading
  `current_user['tenant_id']` directly. Touch points (grep `current_user['tenant_id']` /
  `current_user.get('tenant_id')`):
  `services/network_design_service.py`, `routes/pricing.py` (`/customer`, `/customer` PUT,
  `/component-preview`), `routes/onboarding.py` (via `OnboardingService`), `routes/users.py`
  (`/me`, list), plus billing/lifecycle/cart/quote/order services.
- Keep `user_management_service` cross-tenant logic but feed it the resolved context so the UI
  no longer needs the free-text tenant box.

**New endpoint:** `GET /tenants` (SUPER_ADMIN only) → `[{id, name, tenant_type}]` to populate the switcher.

**Acceptance:** a SUPER_ADMIN with `X-Tenant-Id: <dell>` reads/writes Dell's pricing; a non-super
with the same header gets 403; absent header behaves exactly as today.

---

## 2. Close the authz holes (Phase 0, no schema change)

In `backend/app/routes/pricing.py`, replace the raw `{tenant_id}` path params on
`update_customer_commercial` and `upsert_price_override` with the resolved `TenantContext`
(or assert `role == SUPER_ADMIN or tenant_id == actor_tenant`). Add a shared query helper so
no service can omit the `WHERE tenant_id` clause.

---

## 3. Database changes

All migrations idempotent, run through `backend/app/core/runtime_migrations.py`. Update
`db/schema.sql` to match. **CellHub master tenant id** = the existing CELLHUB tenant; capture it
once for backfills.

### 3a. Add `tenant_id` to global config tables (fully per-tenant)

| Table | Migration |
|---|---|
| `financing_terms` | add `tenant_id UUID FK tenants(id)`, backfill→CellHub, `NOT NULL`; unique `(tenant_id, name)`; partial unique `(tenant_id) WHERE is_default`; index `(tenant_id)` |
| `catalog_items` | add `tenant_id`, backfill, `NOT NULL`; re-key uniqueness per tenant; index `(tenant_id)` |
| `products` | add `tenant_id`, backfill, `NOT NULL`; SKU/name unique per `(tenant_id, …)`; index |
| `product_components` | add `tenant_id`, backfill, `NOT NULL`; index |
| `bundles` | add `tenant_id`, backfill, `NOT NULL`; index |
| `bundle_items` | add `tenant_id`, backfill, `NOT NULL`; index |

Update the SQLAlchemy models in `backend/app/models/{financing,catalog,product}.py` to add the
`tenant_id` mapped column + constraints.

### 3b. New `tenant_settings` (JSONB soft toggles)

```sql
CREATE TABLE IF NOT EXISTS tenant_settings (
  tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  design_ops     JSONB NOT NULL DEFAULT '{}'::jsonb,  -- queue prefs, SLA defaults, auto-assign
  admin_services JSONB NOT NULL DEFAULT '{}'::jsonb,  -- managed-service category toggles
  feature_flags  JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

New model + repository + a `GET/PUT /tenant-settings` route (reads/writes via `TenantContext`).

### 3c. Clone-on-onboard (required by "fully per-tenant rows")

When a new tenant is created, seed its config by cloning the CellHub master tenant's
`financing_terms`, `catalog_items`, `products`/`product_components`/`bundles`, and inserting
default `customer_pricing` + `tenant_settings` rows. Add this to the tenant-creation path
(`OnboardingService` / wherever `tenants` rows are inserted). Catalog-sync (CDW) must run
**per-tenant** going forward — see `routes/catalog.py` / `AdminCatalogSyncPage`.

**Acceptance:** onboarding "Dell" produces a complete, isolated config set; editing Dell's
financing/catalog never affects Walmart or CellHub.

### 3d. RLS hardening (Phase 4)

For every tenant-scoped table:
```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <t>
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
```
Relies on the `SET LOCAL app.current_tenant_id` from §1. Verify pooling uses one txn per request
so `SET LOCAL` scopes correctly. Super-admin cross-tenant works because the GUC carries the
*active* tenant, not the actor's home tenant.

---

## 4. Frontend changes

- **`TenantContext` + `TenantSwitcher`**: dropdown in the top nav, rendered only when
  `user.role === 'SUPER_ADMIN'`; fetches `GET /tenants`; stores `activeTenantId`.
- **Axios interceptor**: attach `X-Tenant-Id: activeTenantId` to every request.
- **`RequireSuperAdmin` guard**: wrap the five views in `frontend/src/router/AppRouter.tsx`:
  `/shop/admin/products`, `/financing`, `/catalog-sync`, `/managed-services`, `/design-submissions`.
- **Remove free-text tenant inputs** in `AdminFinancingPage.tsx` and `AdminUserManagementPage.tsx`;
  read the active tenant from context.
- Keep `/shop/admin/order-notifications` and `/shop/admin/user-access` working, both driven by the
  same active-tenant context.

---

## 5. Domain → table mapping

| Admin view / setting | Backing data | Status |
|---|---|---|
| Pricing | `customer_pricing`, `customer_price_overrides`, per-tenant `products` | scoped; rewire to context |
| Finances | `financing_terms` (→ per-tenant), billing/invoices | financing needs `tenant_id` |
| Admin / managed services | `catalog_items` (→ per-tenant) + `tenant_settings.admin_services` | needs `tenant_id` + JSONB |
| User access | `users` roles/permissions | hierarchy done; drive from switcher |
| Design ops queue | `network_designs` ops + `tenant_settings.design_ops` | scoped + JSONB |
| **Order emails (excluded)** | `tenant_order_notification_settings` | already per-tenant, own page |

---

## 6. Rollout phases

- [ ] **Phase 0** — `tenant_context` dependency + `RequireSuperAdmin` guard + close
      `/pricing/customers/{tenant_id}` authz holes + `GET /tenants`. *(behavior-preserving)*
- [ ] **Phase 1** — schema migrations (§3a), models, backfill to CellHub, clone-on-onboard (§3c).
- [ ] **Phase 2** — frontend tenant switcher + `X-Tenant-Id` interceptor + remove free-text boxes.
- [ ] **Phase 3** — `tenant_settings` JSONB (§3b) for design-ops + admin-services toggles.
- [ ] **Phase 4** — RLS across all tenant tables (§3d).

Each phase ships independently and leaves the app working.

---

## 7. Open items to confirm before/while building

1. **Product catalog duplication.** "Fully per-tenant rows" means each tenant copies the whole
   product/catalog set and CDW sync runs per-tenant. If duplicating the master *product* catalog
   is undesirable, keep `products` shared and make only pricing/financing/managed-services
   per-tenant. Decide before §3a.
2. **SUPER_ADMIN ⇒ CellHub.** Confirm `role == SUPER_ADMIN` always implies CellHub staff, or also
   assert `user_type == 'CELLHUB'` on the cross-tenant path in §1.
3. **CellHub master tenant id** — confirm the canonical id used for all backfills/clone sources.
