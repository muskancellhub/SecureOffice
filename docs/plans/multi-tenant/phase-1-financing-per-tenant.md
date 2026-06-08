# Phase 1 — financing per-tenant + clone-on-onboard  ✅ BUILT

Make **financing the first global table to go per-tenant**, backfill existing rows
to the CellHub master tenant, and seed a new tenant's config when it's created.

> **Status (built 2026-06-05):** all sections below shipped. Implementation notes
> and deviations are in the "What actually shipped" section at the bottom — read it
> before Phase 2.

> **Scope note (shared-catalog decision):** the original plan's §3a added `tenant_id`
> to six tables. With the locked **shared-catalog** decision, Phase 1 touches **only
> `financing_terms`**. `products`, `product_components`, `bundles`, `bundle_items`,
> `catalog_items` **stay global** — do *not* add `tenant_id` to them, and do *not*
> build per-tenant CDW sync. Pricing tables (`customer_pricing`,
> `customer_price_overrides`) are already per-tenant.

## 1. Schema migration (`app/core/runtime_migrations.py`, append to the block)

All idempotent, Postgres. Reference `CELLHUB_MASTER_TENANT_ID` (already imported in
this file from `app.core.tenancy`).

```sql
-- add column nullable first so backfill can run
ALTER TABLE financing_terms ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
-- backfill every existing global row to the master tenant
UPDATE financing_terms SET tenant_id = :master WHERE tenant_id IS NULL;
-- enforce
ALTER TABLE financing_terms ALTER COLUMN tenant_id SET NOT NULL;
-- uniqueness now per-tenant
CREATE UNIQUE INDEX IF NOT EXISTS uq_financing_tenant_name ON financing_terms (tenant_id, name);
-- at most one default per tenant
CREATE UNIQUE INDEX IF NOT EXISTS uq_financing_tenant_default ON financing_terms (tenant_id) WHERE is_default;
CREATE INDEX IF NOT EXISTS idx_financing_tenant ON financing_terms (tenant_id);
```
Pass `{"master": CELLHUB_MASTER_TENANT_ID}` as bind params. Drop any *old* global
unique constraint on `name` if one exists (check `\d financing_terms`).

## 2. Model — `app/models/financing.py`

Add to `FinancingTerms`:
```python
tenant_id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True,
)
```
Add the matching `__table_args__` unique constraints if you mirror them in the model.
Import `ForeignKey` from sqlalchemy.

## 3. Service / repository — make financing reads & writes tenant-aware

Currently `ProductAdminService.list_financing_terms()` /
`create_financing_terms()` (`app/services/product_admin_service.py`) and the routes
in `app/routes/pricing.py` (`GET/POST /financing-terms`) **ignore tenant**.

- Thread the effective tenant in via `get_tenant_context` (Phase 0). Change the two
  financing routes to take `ctx: TenantContext = Depends(get_tenant_context)` and pass
  `ctx.effective_tenant_id` to the service.
- Service methods filter/insert with `tenant_id`. **A shared query helper** so no
  call site can omit the `WHERE tenant_id` clause (the plan calls this out explicitly).
- `ComponentPricingService` already takes `tenant_id` for financing lookups — verify it
  resolves the *active* tenant's default term, not a global one, after this change.

## 4. Clone-on-onboard — `app/services/onboarding_service.py` (or wherever a `Tenant` row is born)

When a **new** tenant is created, seed its isolated config from the master tenant:
1. Clone `financing_terms` rows (copy master's rows with the new `tenant_id`, preserving `is_default`).
2. Insert a default `customer_pricing` row (use `PricingService.get_or_create_customer_pricing`).
3. Insert a `tenant_settings` row **iff Phase 3 has landed** — otherwise skip (Phase 3 backfills).

> **Do NOT clone products/catalog/bundles** — they're shared. This is the key
> divergence from the original §3c.

Tenant rows are currently created in `app/main.py` (demo vendor seed) and
`app/services/auth_service.py` (`register`/vendor signup). Centralize seeding in one
helper (e.g. `TenantProvisioningService.provision(new_tenant_id)`) and call it from
every tenant-creation path so none is missed.

## 5. Acceptance
- Onboarding "Dell" produces Dell-owned `financing_terms` + `customer_pricing` rows.
- Editing Dell's financing never affects Walmart or CellHub (verify with two tenants).
- Existing financing rows are all owned by `CELLHUB_MASTER_TENANT_ID` after migration.
- `GET /pricing/financing-terms` as a SUPER_ADMIN with `X-Tenant-Id: <dell>` returns
  Dell's terms; without the header returns the actor's own.

## Gotchas
- `financing_terms` has a global `is_default` today; the partial unique index makes it
  per-tenant — make sure the backfilled master rows don't have two defaults.
- The migration runner is one big transaction; a failed `SET NOT NULL` (because some row
  didn't backfill) rolls back everything. Backfill must cover 100% before the NOT NULL.
- Tests: add a DB-integration test mirroring `tests/test_product_admin.py`'s skip-without-PG
  fixture, asserting two tenants' financing don't bleed.

---

## What actually shipped

### Files changed
| File | Change |
|------|--------|
| `app/core/runtime_migrations.py` | `financing_terms.tenant_id` add → backfill→master → **two defensive de-dups** (by `(tenant_id, name)` and by per-tenant default) → `SET NOT NULL` → `uq_financing_tenant_name`, partial-unique `uq_financing_tenant_default`, `idx_financing_tenant`. Placed **after** the Phase-0 master-tenant seed so the FK target exists. |
| `app/models/financing.py` | `tenant_id` FK column + `__table_args__` (`UniqueConstraint(tenant_id,name)`, partial `Index(... postgresql_where=text('is_default'))`). |
| `app/services/product_admin_service.py` | `list_financing_terms(tenant_id)` / `create_financing_terms(tenant_id, payload)` now tenant-scoped via a single `_financing_for_tenant()` helper (the "shared query helper so no call site omits the WHERE"). |
| `app/routes/pricing.py` | Both `/financing-terms` routes take `ctx = Depends(get_tenant_context)` and pass `ctx.effective_tenant_id`. |
| `app/services/component_pricing_service.py` | `_default_financing(tenant_id)` filters by tenant **with master-tenant fallback** so pricing never breaks for tenants without their own financing. Call site in `price_product` passes `tenant_id`. |
| `app/services/mix_seed.py` | Seeds the canonical `Standard 36-mo` under the **master tenant**; dedups by **name** (not `is_default`) and self-heals (promotes the 36-mo term if the master lost its default). |
| `app/services/tenant_provisioning_service.py` | **New** `TenantProvisioningService.provision(tenant_id)` — clones master financing (skipping names the tenant already has, and never cloning a second default) + seeds `customer_pricing`. No-op for the master tenant. Uses flush, not commit, so it composes inside signup. |
| `app/services/auth_service.py`, `app/main.py` | Call `provision()` on every tenant-creation path (vendor registration + dev demo seed). |
| `tests/test_product_admin.py` | Updated the financing test to the new `(tenant_id, payload)` signature. |
| `tests/test_tenant_financing_phase1.py` | **New** — isolation + clone-on-onboard + master fallback (DB-integration, skips without PG). |

### Deviations / hard-won notes (read before Phase 2)
- **Two defensive de-dups in the migration are load-bearing.** The shared dev/test
  Postgres had pre-per-tenant rows that all backfilled onto the master tenant, producing
  duplicate `(tenant_id, name)` and multiple defaults. Without the de-dups the unique-index
  creation aborts the *entire* migration transaction. Keep them.
- **`mix_seed` must dedup by name, not `is_default`.** A demoted same-named row otherwise
  causes a `uq_financing_tenant_name` collision on re-seed. It also self-heals a missing
  master default.
- **`provision` never clones a second default.** If the target tenant already has a default
  (or you call it twice), cloned rows come in as `is_default=False`. Idempotent.
- **No `db/schema.sql` change** — `financing_terms` (like `products`/`bundles`) is not in
  `schema.sql`; `runtime_migrations.py` is its source of truth.
- **Existing non-master tenants** keep *no* financing rows after migration (only master is
  backfilled). Pricing still works for them via the master fallback in `_default_financing`;
  they get their own copy on next provision or when a SUPER_ADMIN creates terms via the
  switcher (Phase 2).
- **Behaviour preserved:** `/financing-terms` with no `X-Tenant-Id` resolves to the actor's
  tenant. The pages that call it are already SUPER_ADMIN-gated (Phase 0), so in practice
  super-admins drive them via the switcher in Phase 2.

### Verification
- `pytest tests/test_tenant_financing_phase1.py tests/test_product_admin.py tests/test_component_pricing.py tests/test_component_quote.py tests/test_bundles_capacity.py tests/test_mix_seed.py tests/test_tenant_context.py` → all green.
- Full suite: **20 failed / 90 passed / 0 errors**. The 20 failures are the pre-existing
  `test_unified_catalog_and_bom` + `test_network_design_service` set (`FakeItem` missing
  `managed_service_price` in the already-modified `catalog_service.py`) — unrelated to Phase 1.
