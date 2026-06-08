# Phase 0 — tenant context + authz holes + master tenant  ✅ BUILT

Behaviour-preserving foundation. With no `X-Tenant-Id` header the whole app
behaves exactly as before; the seams the later phases need now exist, and two
real authorization holes are closed.

## What shipped

### Backend

| File | Change |
|------|--------|
| `app/core/tenancy.py` | **New.** `CELLHUB_MASTER_TENANT_ID = '00000000-0000-0000-0000-0000000000c1'`, `CELLHUB_MASTER_TENANT_NAME = 'CellHub'`. Dependency-free so migrations/services/middleware can all import it. |
| `app/middleware/tenant_context.py` | **New.** `TenantContext(effective_tenant_id, is_cross_tenant)`, `resolve_tenant_context()` (pure), `get_tenant_context()` (FastAPI dep reading `X-Tenant-Id` via `Header(alias='X-Tenant-Id')`), `assert_tenant_access()`. Gate = `role == 'SUPER_ADMIN'` only. |
| `app/routes/pricing.py` | Added `assert_tenant_access(current_user, tenant_id)` to `PATCH /pricing/customers/{tenant_id}/commercial` and `POST /pricing/customers/{tenant_id}/price-overrides` — **closes the authz holes** (previously any `manage_pricing` holder could write any tenant's pricing). |
| `app/repositories/tenant_repository.py` | `get_by_id` now tolerates malformed UUIDs (returns `None` → 404 instead of 500). Added `list_all()` ordered by name. |
| `app/routes/tenants.py` + `app/schemas/tenants.py` | **New.** `GET /tenants` → `[{id, name, tenant_type}]`, SUPER_ADMIN-gated (403 otherwise). Registered in `main.py`. |
| `app/core/runtime_migrations.py` | Appended idempotent seed of the canonical CellHub master tenant (insert-if-id-absent). |

### Frontend

| File | Change |
|------|--------|
| `frontend/src/components/RequireSuperAdmin.tsx` | **New.** Redirects non-super users to `/shop`. Sits inside `ProtectedRoute` so `user` is already resolved. |
| `frontend/src/router/AppRouter.tsx` | Wrapped **five** admin views in `<RequireSuperAdmin>`: `/shop/admin/products`, `/financing`, `/catalog-sync`, `/managed-services`, `/design-submissions`. **Left open** (ADMIN-usable, per plan): `/shop/admin/user-access`, `/order-notifications`. |

### Tests

`backend/tests/test_tenant_context.py` — 8 pure-logic tests (fake repo, no DB):
home-tenant resolution, header==home is not cross-tenant, SUPER_ADMIN cross to
existing/missing tenant, non-super forbidden, and the three `assert_tenant_access`
cases. All green.

## Why these choices

- **Path-param assertion, not header rewrite, for the pricing holes.** The plan's §2
  offered "resolve via TenantContext *or* assert role==SUPER_ADMIN/own-tenant". The
  endpoints still take `{tenant_id}` in the path and the current frontend still sends
  it that way, so swapping to the header now would break the contract before Phase 2.
  `assert_tenant_access` closes the hole while preserving today's API shape. Phase 2
  can migrate these to `get_tenant_context` once the switcher sends the header.
- **`resolve_tenant_context` is pure** (takes `requested_tenant_id, current_user, db`)
  so services holding `current_user` can reuse it and it's unit-testable without FastAPI.
- **Seeded master tenant, fixed UUID.** No canonical CellHub row existed (tenants are
  created ad-hoc in `main.py`/`auth_service.py`); a fixed id gives every environment a
  stable backfill/clone source for Phase 1.

## Verification done
- `python -c import` of all touched modules + `app.main`: OK.
- `pytest tests/test_tenant_context.py`: 8 passed.
- Full suite: the 20 pre-existing failures (`test_unified_catalog_and_bom`,
  `test_network_design_service` — `FakeItem` missing `managed_service_price` in the
  already-modified `catalog_service.py`) are unrelated to Phase 0.
- `tsc --noEmit`: my files clean; 2 pre-existing errors live in untouched
  `CustomerDashboardPage.tsx`.

## Phase 0 → 1 handoff notes
- `GET /tenants` returns **all** tenants (CELLHUB/VENDOR/COMPANY). If the switcher
  should hide CellHub/itself, filter client-side or add a query param later.
- The seed migration only runs against Postgres (the runner is PG-only). On a fresh DB
  it inserts the master row; on existing DBs it's a no-op if the id is present.
- Nothing yet calls `get_tenant_context` as a route dependency — it's wired and tested
  but adopted incrementally starting in Phase 1/2.
