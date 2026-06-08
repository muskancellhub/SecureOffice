# Multi-tenant configuration — phased build

Goal: a CellHub `SUPER_ADMIN` selects an active tenant (Dell, Walmart, …) from one
global switcher and configures that tenant's settings in isolation — pricing,
financing, managed services, user access, and the design-ops queue. Order emails
are already per-tenant and stay on their own page (excluded from the unified filter).

This folder is the **handover trail**: one self-contained doc per phase so no
context is lost between sessions. Read this index, then the phase doc you're on.

## Locked decisions (confirmed with the product owner, 2026-06-05)

| # | Decision | Consequence |
|---|----------|-------------|
| **Catalog model** | **Shared catalog.** `products`, `product_components`, `bundles`, `bundle_items`, `catalog_items` stay **global**. Only `financing_terms` + pricing + managed-services toggles become per-tenant. | Drops most of the original §3a. No per-tenant CDW sync. No product/catalog cloning on onboard. |
| **Cross-tenant gate** | `role == 'SUPER_ADMIN'` **only**. We do *not* also assert `user_type == 'CELLHUB'`. | Simpler; assumes every SUPER_ADMIN is CellHub staff. If that ever changes, tighten `tenant_context.SUPER_ADMIN` checks. |
| **Master tenant** | **Seed a canonical CELLHUB row** with a fixed UUID, idempotently, in `runtime_migrations`. | Backfills/clone-source reference `CELLHUB_MASTER_TENANT_ID` — no env dependency, no "pick oldest" fragility. |

## Canonical references (verified in code, Phase 0)

- **Master tenant id**: `backend/app/core/tenancy.py` → `CELLHUB_MASTER_TENANT_ID = '00000000-0000-0000-0000-0000000000c1'`, name `CellHub`. Seeded by `apply_runtime_migrations()`.
- **JWT payload** (`request.state.user`, i.e. `current_user`) carries: `user_id`, `email`, `role`, `user_type`, `tenant_id`, `tenant_type`. Built in `auth_service._issue_tokens_for_user`.
- **Auth seam**: `app/middleware/auth_middleware.py` sets `request.state.user`; `app/middleware/dependencies.py:get_current_user` reads it.
- **Tenant resolution seam**: `app/middleware/tenant_context.py` (`get_tenant_context`, `resolve_tenant_context`, `assert_tenant_access`). This is where the RLS GUC (`SET LOCAL app.current_tenant_id`) hangs off in Phase 4.
- **Exceptions → HTTP**: `AppError`/`ForbiddenError`(403)/`NotFoundError`(404) auto-map via `main.py` exception handler (`@app.exception_handler(AppError)`).
- **Migration runner**: `app/core/runtime_migrations.py` is a single idempotent `apply_runtime_migrations()` under one `with engine.begin() as conn:` block. Postgres-only syntax (`gen_random_uuid`, `JSONB`, `DO $$`). Append new steps at the end of the block.
- **Frontend auth**: `useAuth()` from `frontend/src/context/AuthContext.tsx`; `user: MeResponse` carries `role: 'SUPER_ADMIN' | 'ADMIN' | 'USER'`.

## Tables — current tenancy status

Already tenant-scoped (every row has `tenant_id`): `users`, `quotes`, `orders`,
`contracts`, `subscriptions`, `invoices`, `payments`, `assets`, `network_designs`,
`carts`, `customer_pricing`, `customer_price_overrides`, `list_prices`,
`tenant_order_notification_settings`, `tenant_onboarding`.

Still global — and (given the **shared-catalog** decision) **staying global**:
`catalog_items`, `products`, `product_components`, `bundles`, `bundle_items`.

Now per-tenant as of Phase 1: `financing_terms` (every row has `tenant_id`; existing
rows backfilled to the master tenant). New tenants get a cloned copy via
`TenantProvisioningService.provision()`.

## Phases

| Phase | Doc | Status |
|-------|-----|--------|
| 0 | [phase-0-tenant-context.md](phase-0-tenant-context.md) — tenant-context dependency, `GET /tenants`, `RequireSuperAdmin` guard, close `/pricing/customers/{tenant_id}` authz holes, seed master tenant | ✅ **Built** |
| 1 | [phase-1-financing-per-tenant.md](phase-1-financing-per-tenant.md) — `financing_terms.tenant_id`, backfill→master, model/constraints, `TenantProvisioningService` clone-on-onboard (financing + pricing) | ✅ **Built** |
| 2 | [phase-2-frontend-switcher.md](phase-2-frontend-switcher.md) — TenantSwitcher, `X-Tenant-Id` axios interceptor, remove free-text tenant boxes | ✅ **Built** |
| 3 | [phase-3-tenant-settings-jsonb.md](phase-3-tenant-settings-jsonb.md) — `tenant_settings` JSONB (design-ops + admin-services toggles + feature flags) | ✅ **Built** |
| 4 | [phase-4-rls.md](phase-4-rls.md) — Postgres RLS across all tenant-scoped tables, GUC wiring (behind `ENABLE_RLS`, default off) | ✅ **Built** |

Each phase ships independently and leaves the app working.
